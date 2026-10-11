"""
Ingénieur LMU : ingénieur de course vocal en français pour Le Mans Ultimate.

    python appli.py              -> fenêtre, lit le jeu en direct
    python appli.py --demo       -> fenêtre, lance directement la course de démo
    python appli.py --console    -> sans fenêtre (annonces dans la console)
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo  # noqa: E402
from moteur import CATEGORIES, SPOTTER, URGENT, Annonce, Moteur  # noqa: E402
from voix import Radio  # noqa: E402

HZ = 20
CONFIG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "IngenieurLMU", "reglages.json")


def charger_config() -> dict:
    base = {"categories": list(CATEGORIES), "volume": 100, "debit": 1, "voix": None,
            "chrono_chaque_tour": False, "inverser_cotes": False}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            base.update(json.load(f))
    except Exception:
        pass
    return base


def sauver_config(cfg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class SourceDemo:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.message = "Mode démo : course simulée de 8 tours"

    def lire(self):
        t = time.monotonic() - self.t0
        if t > demo.DUREE:
            self.message = "Démo terminée"
        e = demo.etat(min(t, demo.DUREE))
        e.t = t
        return e


class Boucle:
    """Lit la source à 20 Hz et envoie les annonces à la radio."""

    def __init__(self, radio: Radio, cfg: dict) -> None:
        self.radio = radio
        self.cfg = cfg
        self.source = None
        self.moteur = Moteur(set(cfg["categories"]), cfg["chrono_chaque_tour"])
        self.verrou = threading.Lock()
        threading.Thread(target=self._run, daemon=True, name="boucle").start()

    def demarrer(self, mode: str) -> None:
        with self.verrou:
            self.radio.vider()
            self.moteur = Moteur(set(self.cfg["categories"]), self.cfg["chrono_chaque_tour"])
            if mode == "demo":
                self.source = SourceDemo()
            else:
                from source_lmu import SourceLMU
                self.source = SourceLMU(self.cfg["inverser_cotes"])

    def appliquer_reglages(self) -> None:
        with self.verrou:
            self.moteur.actives = set(self.cfg["categories"])
            self.moteur.chrono_chaque_tour = self.cfg["chrono_chaque_tour"]
            if hasattr(self.source, "inverser"):
                self.source.inverser = self.cfg["inverser_cotes"]

    @property
    def message(self) -> str:
        return getattr(self.source, "message", "Arrêté")

    def _run(self) -> None:
        while True:
            debut = time.perf_counter()
            with self.verrou:
                if self.source is not None:
                    try:
                        e = self.source.lire()
                        for a in self.moteur.maj(e):
                            self.radio.annoncer(a)
                        self.radio.attente_spotter = self.moteur.spotter.actif
                    except Exception as exc:  # la boucle ne doit jamais s'arrêter
                        self.source.message = f"Erreur : {exc}"
            time.sleep(max(0.0, 1.0 / HZ - (time.perf_counter() - debut)))


# ----------------------------------------------------------------------- fenêtre
def fenetre(cfg: dict, mode_initial: str | None) -> None:
    import tkinter as tk
    from tkinter import ttk

    journal: queue.Queue = queue.Queue()
    radio = Radio(journal=lambda texte, prio: journal.put((time.strftime("%H:%M:%S"), texte, prio)))
    radio.regler(volume=cfg["volume"], debit=cfg["debit"], voix=cfg["voix"])
    boucle = Boucle(radio, cfg)

    root = tk.Tk()
    root.title("Ingénieur LMU")
    root.geometry("760x560")
    root.configure(bg="#111418")
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    fond, texte, accent = "#111418", "#e8edf2", "#ff7a1a"
    for w in ("TFrame", "TLabelframe", "TCheckbutton", "TRadiobutton", "TLabel"):
        style.configure(w, background=fond, foreground=texte)
    style.configure("TLabelframe.Label", background=fond, foreground=accent, font=("Segoe UI", 10, "bold"))
    style.configure("Titre.TLabel", font=("Segoe UI", 16, "bold"), foreground=accent)
    style.configure("TButton", font=("Segoe UI", 10, "bold"))

    haut = ttk.Frame(root, padding=10)
    haut.pack(fill="x")
    ttk.Label(haut, text="🎧 Ingénieur LMU", style="Titre.TLabel").pack(side="left")
    etat_var = tk.StringVar(value="Arrêté")
    ttk.Label(haut, textvariable=etat_var).pack(side="right")

    milieu = ttk.Frame(root, padding=(10, 0))
    milieu.pack(fill="x")

    # --- source
    src = ttk.LabelFrame(milieu, text="Source", padding=8)
    src.pack(side="left", fill="y", padx=(0, 8))
    mode = tk.StringVar(value=mode_initial or "jeu")
    ttk.Radiobutton(src, text="Le Mans Ultimate", variable=mode, value="jeu").pack(anchor="w")
    ttk.Radiobutton(src, text="Démo (course simulée)", variable=mode, value="demo").pack(anchor="w")
    ttk.Button(src, text="▶ Démarrer", command=lambda: boucle.demarrer(mode.get())).pack(fill="x", pady=(8, 2))

    # --- voix
    vx = ttk.LabelFrame(milieu, text="Voix", padding=8)
    vx.pack(side="left", fill="y", padx=(0, 8))
    voix_var = tk.StringVar(value=cfg["voix"] or "")
    combo = ttk.Combobox(vx, textvariable=voix_var, state="readonly", width=28)
    combo.pack(fill="x")
    vol = tk.IntVar(value=cfg["volume"])
    deb = tk.IntVar(value=cfg["debit"])
    ttk.Label(vx, text="Volume").pack(anchor="w")
    ttk.Scale(vx, from_=0, to=100, variable=vol, orient="horizontal").pack(fill="x")
    ttk.Label(vx, text="Débit (lent → rapide)").pack(anchor="w")
    ttk.Scale(vx, from_=-3, to=5, variable=deb, orient="horizontal").pack(fill="x")

    def maj_voix(*_):
        cfg.update(volume=int(vol.get()), debit=int(round(deb.get())), voix=voix_var.get() or None)
        radio.regler(volume=cfg["volume"], debit=cfg["debit"], voix=cfg["voix"])
        sauver_config(cfg)

    combo.bind("<<ComboboxSelected>>", maj_voix)
    for v in (vol, deb):
        v.trace_add("write", lambda *_: root.after_idle(maj_voix))
    ttk.Button(vx, text="Tester la voix", command=lambda: radio.annoncer(
        Annonce("Radio OK. Voiture à gauche. Tu es en position 3, écart devant 1,2 seconde.",
                URGENT, "test", 0.0))).pack(fill="x", pady=(8, 0))

    # --- annonces
    an = ttk.LabelFrame(milieu, text="Annonces", padding=8)
    an.pack(side="left", fill="both", expand=True)
    cases = {}

    def maj_cat(*_):
        cfg["categories"] = [c for c, v in cases.items() if v.get()]
        cfg["chrono_chaque_tour"] = chaque_tour.get()
        cfg["inverser_cotes"] = inverser.get()
        boucle.appliquer_reglages()
        sauver_config(cfg)

    for i, (cle, nom) in enumerate(CATEGORIES.items()):
        v = tk.BooleanVar(value=cle in cfg["categories"])
        cases[cle] = v
        ttk.Checkbutton(an, text=nom, variable=v, command=maj_cat).grid(row=i % 5, column=i // 5, sticky="w")
    chaque_tour = tk.BooleanVar(value=cfg["chrono_chaque_tour"])
    inverser = tk.BooleanVar(value=cfg["inverser_cotes"])
    ttk.Checkbutton(an, text="Temps à chaque tour en course", variable=chaque_tour,
                    command=maj_cat).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Checkbutton(an, text="Inverser gauche / droite (spotter)", variable=inverser,
                    command=maj_cat).grid(row=6, column=0, columnspan=2, sticky="w")

    # --- journal radio
    bas = ttk.LabelFrame(root, text="Radio", padding=6)
    bas.pack(fill="both", expand=True, padx=10, pady=10)
    log = tk.Text(bas, bg="#0b0d10", fg=texte, font=("Consolas", 11), relief="flat", wrap="word",
                  state="disabled")
    log.pack(fill="both", expand=True)
    log.tag_configure("spot", foreground="#4fc3f7")
    log.tag_configure("urg", foreground="#ff5252")
    log.tag_configure("heure", foreground="#6b7480")

    voix_chargees = False

    def tic():
        nonlocal voix_chargees
        if not voix_chargees and radio.pret.is_set():
            voix_chargees = True
            noms = radio.moteur.voix_disponibles()
            combo["values"] = noms
            if not voix_var.get() and noms:
                voix_var.set(noms[0])
        while not journal.empty():
            h, txt, prio = journal.get()
            log.configure(state="normal")
            log.insert("end", h + "  ", "heure")
            log.insert("end", txt + "\n", "spot" if prio == SPOTTER else "urg" if prio <= URGENT else "")
            log.see("end")
            log.configure(state="disabled")
        etat_var.set(boucle.message + (f"  —  {radio.info}" if radio.info else ""))
        root.after(100, tic)

    if mode_initial:
        boucle.demarrer(mode_initial)
    else:
        boucle.demarrer("jeu")  # par défaut on écoute le jeu dès l'ouverture
    tic()
    root.mainloop()


def console(cfg: dict, mode: str) -> None:
    radio = Radio(journal=lambda texte, prio: None)
    radio.regler(volume=cfg["volume"], debit=cfg["debit"], voix=cfg["voix"])
    boucle = Boucle(radio, cfg)
    boucle.demarrer(mode)
    print("Ingénieur LMU démarré (Ctrl+C pour quitter)")
    dernier = None
    try:
        while True:
            if boucle.message != dernier:
                dernier = boucle.message
                print(f"[état] {dernier}", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingénieur de course vocal pour Le Mans Ultimate")
    ap.add_argument("--demo", action="store_true", help="lancer la course de démo")
    ap.add_argument("--console", action="store_true", help="sans fenêtre")
    args = ap.parse_args()
    cfg = charger_config()
    mode = "demo" if args.demo else None
    if args.console:
        console(cfg, mode or "jeu")
    else:
        fenetre(cfg, mode)


if __name__ == "__main__":
    main()
