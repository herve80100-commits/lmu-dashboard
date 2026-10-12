"""
Voix française hors ligne.

- Windows : voix SAPI installées (« Microsoft Hortense » sur Windows en français).
- Piper (option) : si un dossier « piper » contenant piper.exe et un modèle
  .onnx est posé à côté de l'exe, il est utilisé à la place (voix plus naturelle).
- Ailleurs (tests, Linux) : affichage dans la console.

Les annonces passent par une file à priorités : le spotter coupe la parole,
les annonces normales attendent qu'aucune voiture ne soit à côté.
"""

from __future__ import annotations

import glob
import hashlib
import heapq
import itertools
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave

from moteur import NORMAL, SPOTTER, URGENT, Annonce


# --------------------------------------------------------------------- moteurs
class VoixConsole:
    nom = "Console"

    def __init__(self, vitesse_lecture: float = 0.0) -> None:
        self.vitesse_lecture = vitesse_lecture  # s par caractère (0 = instantané)

    def voix_disponibles(self) -> list[str]:
        return ["Console"]

    def choisir(self, nom: str) -> None:
        pass

    def regler(self, volume: int, debit: int) -> None:
        pass

    def dire(self, texte: str, stop: threading.Event) -> None:
        if sys.stdout is not None:  # None dans l'exe sans console
            print(f"[radio] {texte}", flush=True)
        fin = time.monotonic() + len(texte) * self.vitesse_lecture
        while time.monotonic() < fin and not stop.is_set():
            time.sleep(0.02)


class VoixSAPI:
    """Voix Windows. Tous les appels COM se font dans le fil de la voix."""

    nom = "Windows"

    def __init__(self) -> None:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        self.sp = win32com.client.Dispatch("SAPI.SpVoice")
        self._voix = {}
        for tok in self.sp.GetVoices():
            self._voix[tok.GetDescription()] = tok
        francaises = [n for n, tok in self._voix.items() if self._est_fr(tok)]
        if francaises:
            self.sp.Voice = self._voix[francaises[0]]
        self.francais = bool(francaises)

    @staticmethod
    def _est_fr(tok) -> bool:
        try:
            langue = tok.GetAttribute("Language") or ""
        except Exception:
            langue = ""
        return any(c.lower() in ("40c", "c0c", "80c", "100c", "140c") for c in langue.split(";")) \
            or "french" in tok.GetDescription().lower() or "fran" in tok.GetDescription().lower()

    def voix_disponibles(self) -> list[str]:
        fr = [n for n, t in self._voix.items() if self._est_fr(t)]
        return fr + [n for n in self._voix if n not in fr]

    def choisir(self, nom: str) -> None:
        if nom in self._voix:
            self.sp.Voice = self._voix[nom]

    def regler(self, volume: int, debit: int) -> None:
        self.sp.Volume = max(0, min(100, int(volume)))
        self.sp.Rate = max(-10, min(10, int(debit)))

    def dire(self, texte: str, stop: threading.Event) -> None:
        self.sp.Speak(texte, 1 | 2)  # asynchrone + vide ce qui était en cours
        while not self.sp.WaitUntilDone(30):
            if stop.is_set():
                self.sp.Speak("", 1 | 2)
                return


class VoixPiper:
    """Piper (https://github.com/rhasspy/piper) : synthèse locale mise en cache."""

    nom = "Piper"

    def __init__(self, dossier: str) -> None:
        import winsound  # noqa: F401  (Windows uniquement)

        self.exe = os.path.join(dossier, "piper.exe")
        modeles = sorted(glob.glob(os.path.join(dossier, "*.onnx")))
        if not os.path.isfile(self.exe) or not modeles:
            raise FileNotFoundError("piper.exe ou modèle .onnx introuvable")
        self.modeles = {os.path.basename(m): m for m in modeles}
        self.modele = modeles[0]
        self.cache = os.path.join(tempfile.gettempdir(), "ingenieur_lmu_piper")
        os.makedirs(self.cache, exist_ok=True)
        self.volume = 100
        self.debit = 0

    def voix_disponibles(self) -> list[str]:
        return list(self.modeles)

    def choisir(self, nom: str) -> None:
        self.modele = self.modeles.get(nom, self.modele)

    def regler(self, volume: int, debit: int) -> None:
        self.volume, self.debit = volume, debit

    def _wav(self, texte: str) -> str:
        echelle = round(1.0 - self.debit * 0.05, 2)  # débit + => plus rapide
        h = hashlib.md5(f"{self.modele}|{echelle}|{texte}".encode()).hexdigest()
        chemin = os.path.join(self.cache, h + ".wav")
        if not os.path.exists(chemin):
            subprocess.run(
                [self.exe, "--model", self.modele, "--output_file", chemin, "--length_scale", str(echelle)],
                input=texte.encode("utf-8"), capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        return chemin

    def preparer(self, textes) -> None:
        for t in textes:
            try:
                self._wav(t)
            except Exception:
                pass

    def dire(self, texte: str, stop: threading.Event) -> None:
        import winsound

        chemin = self._wav(texte)
        with wave.open(chemin) as w:
            duree = w.getnframes() / float(w.getframerate())
        winsound.PlaySound(chemin, winsound.SND_FILENAME | winsound.SND_ASYNC)
        fin = time.monotonic() + duree
        while time.monotonic() < fin:
            if stop.is_set():
                winsound.PlaySound(None, 0)
                return
            time.sleep(0.02)


PHRASES_SPOTTER = ("Voiture à gauche", "Voiture à droite", "Trois de front, tu es au milieu",
                   "Dégagé à gauche", "Dégagé à droite", "Dégagé", "Toujours là")


def dossier_appli() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------- la radio
class Radio:
    """File d'annonces + fil de lecture."""

    def __init__(self, moteur_voix: str = "auto", journal=None) -> None:
        self.choix = moteur_voix
        self.journal = journal or (lambda texte, prio: None)
        self.file: list = []
        self.compteur = itertools.count()
        self.verrou = threading.Condition()
        self.couper = threading.Event()
        self.en_cours: Annonce | None = None
        self.attente_spotter = False  # voiture à côté : on garde les annonces normales
        self.reglages = {"volume": 100, "debit": 1, "voix": None}
        self.moteur = None
        self.pret = threading.Event()
        self.info = ""
        threading.Thread(target=self._boucle, daemon=True, name="radio").start()

    # appelé depuis n'importe quel fil
    def annoncer(self, a: Annonce) -> None:
        with self.verrou:
            if a.priorite == SPOTTER:
                # le spotter remplace les anciens messages spotter et coupe la parole
                self.file = [x for x in self.file if x[2].priorite != SPOTTER]
                heapq.heapify(self.file)
                if self.en_cours is not None:
                    self.couper.set()
            elif any(x[2].texte == a.texte for x in self.file):
                return
            heapq.heappush(self.file, (a.priorite, next(self.compteur), a, time.monotonic()))
            self.verrou.notify()

    def regler(self, **kw) -> None:
        with self.verrou:
            self.reglages.update(kw)
            self.reglages["_maj"] = True
            self.verrou.notify()

    def vider(self) -> None:
        with self.verrou:
            self.file = []
            self.couper.set()

    def _creer_moteur(self):
        choix = self.choix
        if choix in ("auto", "piper") and sys.platform == "win32":
            try:
                m = VoixPiper(os.path.join(dossier_appli(), "piper"))
                m.preparer(PHRASES_SPOTTER)
                return m
            except Exception:
                pass
        if choix in ("auto", "windows", "piper") and sys.platform == "win32":
            try:
                return VoixSAPI()
            except Exception as exc:
                self.info = f"Voix Windows indisponible ({exc}), affichage seul."
        return VoixConsole()

    def _boucle(self) -> None:
        self.moteur = self._creer_moteur()
        if isinstance(self.moteur, VoixSAPI) and not self.moteur.francais:
            self.info = "Aucune voix française Windows trouvée : installe le pack vocal français (Paramètres > Heure et langue > Voix)."
        self.reglages["_maj"] = True
        self.pret.set()
        while True:
            with self.verrou:
                while True:
                    if self.reglages.pop("_maj", False):
                        try:
                            if self.reglages.get("voix"):
                                self.moteur.choisir(self.reglages["voix"])
                            self.moteur.regler(self.reglages["volume"], self.reglages["debit"])
                        except Exception:
                            pass
                    item = self._prochain()
                    if item is not None:
                        break
                    self.verrou.wait(0.1)
                self.en_cours = item
                self.couper.clear()
            try:
                self.journal(item.texte, item.priorite)
                self.moteur.dire(item.texte, self.couper)
            except Exception as exc:
                self.info = f"Erreur de voix : {exc}"
            finally:
                with self.verrou:
                    self.en_cours = None

    def _prochain(self) -> Annonce | None:
        maintenant = time.monotonic()
        garde = []
        choisi = None
        while self.file:
            prio, n, a, recu = heapq.heappop(self.file)
            if maintenant - recu > a.duree_vie:
                continue  # trop vieux, plus d'actualité
            if self.attente_spotter and prio >= NORMAL:
                garde.append((prio, n, a, recu))
                continue
            choisi = a
            break
        for g in garde:
            heapq.heappush(self.file, g)
        return choisi


__all__ = ["Radio", "VoixConsole", "PHRASES_SPOTTER", "URGENT", "dossier_appli"]
