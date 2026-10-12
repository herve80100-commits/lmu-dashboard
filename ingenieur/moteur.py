"""
Moteur d'annonces : compare l'état de course d'un instant au précédent et
décide quoi dire, quand, et avec quelle urgence (dans l'esprit de CrewChief).

Priorités : 0 = spotter (coupe la parole), 1 = urgent, 2 = normal, 3 = info.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from etat import ROUES, Etat, chrono, nombre, place, secondes
from etat import secondes as secteurs_txt

SPOTTER, URGENT, NORMAL, INFO = 0, 1, 2, 3

CATEGORIES = {
    "spotter": "Spotter (voitures à côté)",
    "course": "Course (départ, positions, fin)",
    "ecarts": "Écarts devant / derrière",
    "chrono": "Temps au tour",
    "carburant": "Carburant et énergie",
    "pneus": "Pneus et freins",
    "meca": "Moteur et dégâts",
    "drapeaux": "Drapeaux et pénalités",
    "stands": "Stands",
}


@dataclass
class Annonce:
    texte: str
    priorite: int
    categorie: str
    t: float
    duree_vie: float = 10.0  # au-delà, l'annonce n'a plus de sens


class Spotter:
    """Voiture à gauche / à droite / trois de front / dégagé."""

    LONGUEUR = 5.5  # m : chevauchement (longueur d'une voiture + marge)
    ANTICIPATION = 1.0  # s : on prévient 1 s avant que la voiture arrive à ta hauteur
    PORTEE = 40.0  # m : distance max suivie
    LARGEUR_MAX = 5.5  # m : au-delà, la voiture n'est pas « à côté »
    LARGEUR_MIN = 0.8  # m : en dessous, c'est la même ligne (devant/derrière)
    DELAI_DEGAGE = 1.0  # s sans voiture avant d'annoncer « dégagé »
    TOUJOURS_LA = 6.0  # s de chevauchement avant « toujours là »

    def __init__(self) -> None:
        self.gauche = self.droite = False
        self.vu_g = self.vu_d = -1e9  # dernier instant où une voiture était là
        self.depuis = 0.0
        self.rappel_fait = False
        self.prec = {}  # id -> (t, lon) pour la vitesse relative

    @property
    def actif(self) -> bool:
        return self.gauche or self.droite

    def maj(self, e: Etat) -> list[str]:
        if e.vitesse < 15 or e.au_stand:
            g = d = False
            self.vu_g = self.vu_d = -1e9
        else:
            g = d = False
            prec, self.prec = self.prec, {}
            for i, v in enumerate(e.voisins):
                lat, lon = v[0], v[1]
                vid = v[2] if len(v) > 2 else i
                if abs(lon) > self.PORTEE or not (self.LARGEUR_MIN < abs(lat) < self.LARGEUR_MAX):
                    continue
                # vitesse de rapprochement (m/s) mesurée entre deux lectures
                rapproche = 0.0
                old = prec.get(vid)
                if old and e.t - old[0] > 0.01 and e.t - old[0] < 1.0:
                    dlon = (abs(old[1]) - abs(lon)) / (e.t - old[0])
                    rapproche = dlon
                    self.prec[vid] = old if e.t - old[0] < 0.15 else (e.t, lon)
                else:
                    self.prec[vid] = (e.t, lon)
                marge = self.LONGUEUR + max(0.0, rapproche) * self.ANTICIPATION
                if abs(lon) < marge:
                    if lat > 0:
                        g = True
                    else:
                        d = True
            if g:
                self.vu_g = e.t
            if d:
                self.vu_d = e.t
            # « dégagé » seulement après un court délai (évite les clignotements)
            g = g or (self.gauche and e.t - self.vu_g < self.DELAI_DEGAGE)
            d = d or (self.droite and e.t - self.vu_d < self.DELAI_DEGAGE)

        msgs = []
        avant = (self.gauche, self.droite)
        if (g, d) != avant:
            if g and d:
                msgs.append("Trois de front, tu es au milieu")
            elif g and not d:
                msgs.append("Dégagé à droite" if avant == (True, True) else "Voiture à gauche")
            elif d and not g:
                msgs.append("Dégagé à gauche" if avant == (True, True) else "Voiture à droite")
            else:
                msgs.append("Dégagé")
            if (g or d) and not any(avant):
                self.depuis = e.t
                self.rappel_fait = False
            self.gauche, self.droite = g, d
        elif (g or d) and not self.rappel_fait and e.t - self.depuis > self.TOUJOURS_LA:
            self.rappel_fait = True
            msgs.append("Toujours là")
        return msgs


class Moteur:
    def __init__(self, actives: set[str] | None = None, chrono_chaque_tour: bool = False) -> None:
        self.actives = set(actives) if actives is not None else set(CATEGORIES)
        self.chrono_chaque_tour = chrono_chaque_tour
        self.reset()

    # ------------------------------------------------------------------ outils
    def reset(self) -> None:
        self.prec: Etat | None = None
        self.cle = None
        self.spotter = Spotter()
        self.cooldown: dict[str, float] = {}
        self.sortie: list[Annonce] = []
        self.bienvenue = False
        # tours
        self.tour_en_attente = None  # instant de passage de ligne en attente du chrono
        self.chrono_avant = None
        self.meilleur = None
        self.tours_propres: list[float] = []
        self.invalide_annonce = False
        # carburant
        self.carbu_debut = None
        self.energie_debut = None
        self.tour_stand = False
        self.conso: list[float] = []
        self.conso_ve: list[float] = []
        self.alerte_carbu = None
        # position / écarts
        self.pos_annoncee = None
        self.pos_vue = None
        self.pos_depuis = 0.0
        self.ecarts_hist: list[tuple] = []  # (devant, derrière) à chaque passage
        self.alerte_derriere = False
        # session
        self.seuils_temps_faits: set[int] = set()
        self.seuils_tours_faits: set[int] = set()
        self.dernier_tour_annonce = False
        self.fini_annonce = False
        self.usure_seuils: set[float] = set()
        self.crevaisons: set[int] = set()
        self.detaches: set[int] = set()

    def _dire(self, e: Etat, texte: str, prio: int, cat: str, cle: str | None = None,
              attente: float = 0.0, vie: float = 10.0) -> None:
        if cat not in self.actives:
            return
        if cle is not None:
            if e.t < self.cooldown.get(cle, -1e9):
                return
            self.cooldown[cle] = e.t + attente
        self.sortie.append(Annonce(texte, prio, cat, e.t, vie))

    # ------------------------------------------------------------- point d'entrée
    def maj(self, e: Etat) -> list[Annonce]:
        self.sortie = []
        if not e.connecte:
            self.prec = None
            return []
        if e.cle != self.cle:
            self.reset()
            self.cle = e.cle
        p = self.prec
        if p is None:
            if not self.bienvenue:
                self.bienvenue = True
                txt = "Radio OK, je suis avec toi."
                if e.temp_piste is not None:
                    txt += f" Piste à {round(e.temp_piste)} degrés, air à {round(e.temp_air or 0)}."
                self._dire(e, txt, NORMAL, "course")
                self._froid(e)
            self._init_tour(e)
            self.meilleur = e.meilleur_tour
            self.prec = e
            return self.sortie

        for msg in self.spotter.maj(e):
            self._dire(e, msg, SPOTTER, "spotter", vie=1.0)

        self._phases(p, e)
        self._drapeaux(p, e)
        self._stands(p, e)
        self._mecanique(p, e)
        self._pneus_immediat(p, e)
        self._position(p, e)
        self._ecart_derriere(e)
        self._temps_restant(e)
        self._invalide(p, e)
        self._meteo(p, e)

        if e.tours_faits > p.tours_faits:
            self._passage_ligne(p, e)
        if e.au_stand or e.etat_stand in (2, 3):
            self.tour_stand = True
        if self.tour_en_attente is not None:
            self._chrono(e)

        self.prec = e
        return self.sortie

    # ------------------------------------------------------------ phases / départ
    def _phases(self, p: Etat, e: Etat) -> None:
        course = e.session == "course"
        if e.phase != p.phase:
            if e.phase == 3 and course:
                self._dire(e, "Tour de formation. Chauffe bien les pneus et les freins.", NORMAL, "course")
            elif e.phase == 4 and course:
                self._dire(e, "Les feux s'allument, prépare-toi.", URGENT, "course")
            elif e.phase == 5 and p.phase == 4 and course:
                self._dire(e, "Feu vert, feu vert, feu vert !", URGENT, "course", vie=3)
            elif e.phase == 5 and p.phase == 6:
                self._dire(e, "Drapeau vert, drapeau vert, la course reprend !", URGENT, "drapeaux")
            elif e.phase == 6:
                self._dire(e, "Full course yellow, voiture de sécurité. Ralentis, on ne double plus.",
                           URGENT, "drapeaux")
            elif e.phase == 7:
                self._dire(e, "Drapeau rouge, la session est arrêtée.", URGENT, "drapeaux")
        if e.fcy != p.fcy and e.phase == 6:
            if e.fcy == 4:
                self._dire(e, "La voie des stands est ouverte.", NORMAL, "drapeaux")
            elif e.fcy == 2:
                self._dire(e, "Stands fermés pendant la neutralisation.", NORMAL, "drapeaux")
            elif e.fcy == 5:
                self._dire(e, "La voiture de sécurité rentre à la fin de ce tour.", URGENT, "drapeaux")
        if e.termine and not p.termine and not self.fini_annonce:
            self.fini_annonce = True
            if course and e.position:
                txt = f"Drapeau à damier ! Tu termines {place(e.position)}."
                if e.position == 1:
                    txt += " Victoire, bravo !"
                elif e.position <= 3:
                    txt += " Podium, superbe course !"
                else:
                    txt += " Belle course."
            else:
                txt = "Drapeau à damier, fin de la session."
            self._dire(e, txt, URGENT, "course", vie=30)

    # ------------------------------------------------------------------ drapeaux
    def _drapeaux(self, p: Etat, e: Etat) -> None:
        if e.drapeau_bleu and not p.drapeau_bleu:
            self._dire(e, "Drapeau bleu, laisse passer la voiture derrière.", URGENT, "drapeaux",
                       cle="bleu", attente=30)
        if e.sous_jaune and not p.sous_jaune and e.phase == 5:
            self._dire(e, "Drapeau jaune, prudence, voiture lente ou arrêtée devant.", URGENT, "drapeaux",
                       cle="jaune", attente=15)
        elif p.sous_jaune and not e.sous_jaune and e.phase == 5:
            self._dire(e, "Piste dégagée.", NORMAL, "drapeaux", cle="vert", attente=15)
        if e.phase == 5:
            prochain = e.secteur % 3  # index du secteur suivant (0 = S1)
            for i in (e.secteur - 1, prochain):
                if e.secteurs_jaunes[i] and not p.secteurs_jaunes[i]:
                    ou = "dans ce secteur" if i == e.secteur - 1 else f"au secteur {i + 1}, devant toi"
                    self._dire(e, f"Drapeau jaune {ou}.", URGENT, "drapeaux", cle=f"sj{i}", attente=20)
        if e.penalites > p.penalites:
            self._dire(e, "Pénalité ! Tu dois passer par les stands.", URGENT, "drapeaux")
        elif e.penalites < p.penalites:
            self._dire(e, "Pénalité purgée.", NORMAL, "drapeaux")
        if e.limites_pas > p.limites_pas:
            if e.limites_par_penalite > 0:
                reste = e.limites_par_penalite - e.limites_pas
                txt = (f"Limites de piste, avertissement {e.limites_pas} sur {e.limites_par_penalite}."
                       if reste > 0 else "Limites de piste, attention à la pénalité.")
            else:
                txt = "Attention aux limites de piste."
            self._dire(e, txt, URGENT, "drapeaux", cle="limites", attente=5)

    def _invalide(self, p: Etat, e: Etat) -> None:
        if e.session != "course" and e.tour_invalide and not p.tour_invalide and not self.invalide_annonce:
            self.invalide_annonce = True
            self._dire(e, "Tour invalidé.", NORMAL, "chrono")

    # -------------------------------------------------------------------- stands
    def _stands(self, p: Etat, e: Etat) -> None:
        if e.etat_stand != p.etat_stand:
            if e.etat_stand == 1:
                self._dire(e, "Arrêt aux stands noté, on t'attend à ce tour.", NORMAL, "stands")
            elif e.etat_stand == 4:
                txt = "Sortie des stands, attention au trafic."
                conso = sum(self.conso) / len(self.conso) if self.conso else None
                reste = self._tours_restants_course(e)
                if conso and reste:
                    tours = e.carburant / conso
                    txt += (f" Tu as {round(e.carburant)} litres, assez pour finir." if tours >= reste + 0.3
                            else f" Tu as {round(e.carburant)} litres, de quoi faire {int(tours)} tours.")
                self._dire(e, txt, NORMAL, "stands")
        if p.au_stand and not e.au_stand:
            self._froid(e)
        if (e.etat_stand == 2 or (e.au_stand and not p.au_stand)) and not e.limiteur and e.vitesse > 70:
            self._dire(e, "Limiteur ! Limiteur !", URGENT, "stands", cle="limiteur", attente=6, vie=3)

    def _froid(self, e: Etat) -> None:
        pn = [x for x in e.pneus]
        opt = pn[0].optimal or 85.0
        froids = sum(x.temp for x in pn) / 4 < min(opt - 30, 55)
        freins = max(x.frein for x in pn) < 250
        if froids or freins:
            quoi = " et ".join(m for m, c in (("pneus", froids), ("freins", freins)) if c)
            self._dire(e, f"Attention, {quoi} froids, vas-y doucement ce tour.", NORMAL, "pneus",
                       cle="froid_sortie", attente=30)

    # ---------------------------------------------------------------- mécanique
    def _mecanique(self, p: Etat, e: Etat) -> None:
        if e.surchauffe or e.eau > 110 or e.huile > 130:
            self._dire(e, f"Le moteur chauffe : eau à {round(e.eau)} degrés, huile à {round(e.huile)}.",
                       URGENT, "meca", cle="moteur", attente=90)
        if e.degats > p.degats:
            gros = e.degats - p.degats >= 3 or e.degats >= 8
            txt = "Gros choc ! Vérifie les dégâts, pense à rentrer." if gros else "Petit choc, dégâts légers."
            self._dire(e, txt, URGENT if gros else NORMAL, "meca", cle="degats", attente=8)

    def _pneus_immediat(self, p: Etat, e: Etat) -> None:
        for i, (a, b) in enumerate(zip(p.pneus, e.pneus)):
            if b.detache and i not in self.detaches:
                self.detaches.add(i)
                self._dire(e, f"Tu as perdu la roue {ROUES[i]} ! Rentre doucement.", URGENT, "pneus")
            elif b.crevaison and i not in self.crevaisons:
                self.crevaisons.add(i)
                self._dire(e, f"Crevaison {ROUES[i]} ! Rentre aux stands.", URGENT, "pneus")
            if not b.crevaison:
                self.crevaisons.discard(i)
        avant = max(e.pneus[0].frein, e.pneus[1].frein)
        arriere = max(e.pneus[2].frein, e.pneus[3].frein)
        if max(avant, arriere) > 1000 and e.vitesse > 50:
            ou = "avant" if avant >= arriere else "arrière"
            self._dire(e, f"Freins {ou} très chauds, {round(max(avant, arriere))} degrés.",
                       NORMAL, "pneus", cle="freins", attente=60)

    def _meteo(self, p: Etat, e: Etat) -> None:
        if e.pluie >= 0.1 > p.pluie:
            self._dire(e, "Il commence à pleuvoir.", NORMAL, "course", cle="pluie", attente=60)
        elif p.pluie >= 0.05 > e.pluie:
            self._dire(e, "La pluie s'arrête.", INFO, "course", cle="pluie", attente=60)

    # ----------------------------------------------------------------- position
    @staticmethod
    def _general(e: Etat) -> str:
        if e.position_generale and e.nb_total > e.nb_classe:
            return f", {e.position_generale} au général"
        return ""

    def _secteurs(self, e: Etat) -> None:
        """Compare les secteurs du tour à tes meilleurs secteurs."""
        if not e.secteurs:
            return
        best = getattr(self, "best_secteurs", None)
        if best:
            diffs = [s - b for s, b in zip(e.secteurs, best)]
            vite = min(range(3), key=lambda i: diffs[i])
            lent = max(range(3), key=lambda i: diffs[i])
            parts = []
            if diffs[vite] < -0.05:
                parts.append(f"Plus rapide au secteur {vite + 1}, {secteurs_txt(-diffs[vite])} de mieux")
            if diffs[lent] > 0.1 and lent != vite:
                parts.append(f"tu perds {secteurs_txt(diffs[lent])} au secteur {lent + 1}")
            if parts:
                txt = ", ".join(parts)
                self._dire(e, txt[0].upper() + txt[1:] + ".", INFO, "chrono", vie=20)
        self.best_secteurs = [min(a, b) for a, b in zip(best, e.secteurs)] if best else list(e.secteurs)

    def _position(self, p: Etat, e: Etat) -> None:
        if e.session != "course" or not e.position or e.phase not in (5, 6):
            self.pos_annoncee = e.position or self.pos_annoncee
            return
        if self.pos_annoncee is None:
            self.pos_annoncee = e.position
        if e.position != self.pos_vue:
            self.pos_vue = e.position
            self.pos_depuis = e.t
        # une position doit tenir 2 s avant d'être annoncée (évite les allers-retours)
        if e.position != self.pos_annoncee and e.t - self.pos_depuis >= 2.0:
            gagne = e.position < self.pos_annoncee
            debut = "Position gagnée" if gagne else "Position perdue"
            self._dire(e, f"{debut}, tu es {place(e.position)} en catégorie{self._general(e)}.", NORMAL, "course")
            self.pos_annoncee = e.position
            self.ecarts_hist = []  # ce ne sont plus les mêmes voitures devant / derrière

    def _ecart_derriere(self, e: Etat) -> None:
        if e.session != "course" or e.ecart_derriere is None or e.au_stand:
            return
        if e.ecart_derriere < 1.0 and not self.alerte_derriere and e.phase == 5:
            self.alerte_derriere = True
            self._dire(e, "La voiture derrière est à moins d'une seconde, défends.", NORMAL, "ecarts",
                       cle="derriere", attente=60)
        elif e.ecart_derriere > 1.6:
            self.alerte_derriere = False

    # ---------------------------------------------------------- temps restant
    def _temps_restant(self, e: Etat) -> None:
        if e.temps_restant is None or e.phase != 5:
            return
        for m in (30, 15, 10, 5, 2, 1):
            if e.temps_restant <= m * 60 and m not in self.seuils_temps_faits:
                self.seuils_temps_faits.update(x for x in (30, 15, 10, 5, 2, 1) if x >= m)
                # pas d'annonce si la session commence déjà sous ce seuil
                if e.temps_restant > m * 60 - 20:
                    txt = "Plus qu'une minute." if m == 1 else f"Plus que {m} minutes."
                    self._dire(e, txt, NORMAL, "course")
                break

    # ------------------------------------------------------------ passage de ligne
    def _init_tour(self, e: Etat) -> None:
        self.carbu_debut = e.carburant
        self.energie_debut = e.energie
        self.tour_stand = e.au_stand
        self.chrono_avant = e.dernier_tour

    def _passage_ligne(self, p: Etat, e: Etat) -> None:
        # consommation (tours sans passage aux stands seulement)
        if not self.tour_stand and self.carbu_debut is not None:
            used = self.carbu_debut - e.carburant
            if 0.05 < used < 50:
                self.conso = (self.conso + [used])[-3:]
            if e.energie is not None and self.energie_debut is not None:
                used_ve = self.energie_debut - e.energie
                if 0.001 < used_ve < 1:
                    self.conso_ve = (self.conso_ve + [used_ve])[-3:]
        stand = self.tour_stand
        self._init_tour(e)
        self.chrono_avant = p.dernier_tour  # le nouveau chrono arrive parfois juste après
        self.tour_en_attente = (e.t, stand)
        self.invalide_annonce = False

        self._fin_de_course(e)
        if not e.termine:
            self._carburant(e)
            self._pneus_tour(e)

    def _tours_restants_course(self, e: Etat) -> float | None:
        """Tours qu'il reste à faire (estimation), course uniquement."""
        if e.session != "course":
            return None
        if e.tours_max:
            return max(0, e.tours_max - e.tours_faits)
        if e.temps_restant is not None:
            ref = self._tour_moyen()
            if ref:
                return math.ceil(max(0.0, e.temps_restant) / ref)
        return None

    def _tour_moyen(self) -> float | None:
        t = self.tours_propres[-3:]
        return sum(t) / len(t) if t else None

    def _fin_de_course(self, e: Etat) -> None:
        if e.session != "course" or e.termine:
            return
        reste = None
        if e.tours_max:
            reste = e.tours_max - e.tours_faits
        elif e.temps_restant is not None and e.temps_restant <= 0:
            reste = 1
        if reste == 1 and not self.dernier_tour_annonce:
            self.dernier_tour_annonce = True
            self._dire(e, f"Dernier tour ! Tu es {place(e.position)}, ramène-la.", URGENT, "course")
        elif e.tours_max and reste in (2, 5, 10) and reste not in self.seuils_tours_faits:
            self.seuils_tours_faits.add(reste)
            self._dire(e, f"Encore {reste} tours.", NORMAL, "course")

    def _chrono(self, e: Etat) -> None:
        t0, stand = self.tour_en_attente
        nouveau = e.dernier_tour is not None and e.dernier_tour > 0 and e.dernier_tour != self.chrono_avant
        if not nouveau:
            if e.t - t0 > 3:
                self.tour_en_attente = None  # pas de chrono (tour annulé, sortie des stands…)
            return
        self.tour_en_attente = None
        lap = e.dernier_tour
        if not stand:
            self.tours_propres = (self.tours_propres + [lap])[-5:]
        course = e.session == "course"
        ancien = self.meilleur
        self.meilleur = min(x for x in (ancien, lap) if x) if ancien else lap
        if ancien is None or lap < ancien - 0.0005:
            if ancien is not None:
                txt = f"Meilleur tour ! {chrono(lap)}, {secondes(ancien - lap)} de mieux."
                self._dire(e, txt, NORMAL, "chrono")
            elif not stand:
                self._dire(e, f"Tour en {chrono(lap)}.", INFO, "chrono")
        elif not course or self.chrono_chaque_tour:
            self._dire(e, f"{chrono(lap)}, {secondes(lap - ancien)} plus lent.", INFO, "chrono")
        if not stand:
            self._secteurs(e)
        if course:
            self._ecarts_periodiques(e)
            if e.tours_faits % 2 == 0 and e.position:
                self._dire(e, f"Classement : tu es {place(e.position)} en catégorie{self._general(e)}.", INFO,
                           "course", vie=20)

    # ------------------------------------------------------------------- écarts
    def _ecarts_periodiques(self, e: Etat) -> None:
        if e.phase != 5 or e.tours_faits < 1:
            return
        self.ecarts_hist.append((e.ecart_devant, e.ecart_derriere))
        n = len(self.ecarts_hist)
        parts = []
        if n >= 3:
            d0, b0 = self.ecarts_hist[-3]
            d1, b1 = self.ecarts_hist[-1]
            if d0 is not None and d1 is not None and e.position > 1:
                diff = d1 - d0
                if diff <= -0.5:
                    parts.append(f"Tu reprends {secondes(-diff / 2)} par tour sur la voiture devant, "
                                 f"elle est à {secondes(d1)}.")
                elif diff >= 0.5:
                    parts.append(f"La voiture devant s'échappe, elle est à {secondes(d1)}.")
            if b0 is not None and b1 is not None and e.position < e.nb_classe:
                diff = b1 - b0
                if diff <= -0.5:
                    parts.append(f"La voiture derrière revient, elle est à {secondes(b1)}.")
        if not parts:
            if e.ecart_devant is not None and e.position > 1:
                parts.append(f"Écart devant {secondes(e.ecart_devant)}.")
            if e.ecart_derriere is not None and e.position < e.nb_classe:
                parts.append(f"Derrière, {secondes(e.ecart_derriere)}.")
        if parts:
            self._dire(e, " ".join(parts), INFO, "ecarts", vie=20)

    # ---------------------------------------------------------------- carburant
    def _carburant(self, e: Etat) -> None:
        conso = sum(self.conso) / len(self.conso) if self.conso else None
        conso_ve = sum(self.conso_ve) / len(self.conso_ve) if self.conso_ve else None
        tours_carbu = e.carburant / conso if conso else None
        tours_ve = e.energie / conso_ve if conso_ve and e.energie is not None else None
        options = [x for x in (tours_carbu, tours_ve) if x is not None]
        if not options:
            return
        tours = min(options)
        par_ve = tours_ve is not None and tours == tours_ve
        quoi = "d'énergie" if par_ve else "d'essence"

        # alertes niveau bas (une fois par seuil)
        for seuil, txt in ((1, f"Plus qu'un tour {quoi} ! Rentre aux stands à ce tour."),
                           (2, f"Il te reste 2 tours {quoi}."),
                           (4, f"Carburant bas : 4 tours {quoi}.")):
            if tours < seuil + 0.5:
                if self.alerte_carbu is None or seuil < self.alerte_carbu:
                    self.alerte_carbu = seuil
                    self._dire(e, txt, URGENT if seuil <= 2 else NORMAL, "carburant")
                return
        self.alerte_carbu = None  # on a refait le plein

        n = len(self.conso_ve if par_ve else self.conso)
        if n == 1 or (e.tours_faits % 5 == 0):
            if par_ve:
                txt = (f"Énergie : {nombre(conso_ve * 100)} pour cent par tour, "
                       f"de quoi faire {int(tours)} tours.")
            else:
                txt = f"Consommation {nombre(conso)} litres par tour, de quoi faire {int(tours)} tours."
            reste = self._tours_restants_course(e)
            if reste is not None and reste > 0:
                manque = reste - tours
                if manque <= -0.3:
                    txt += " Assez pour finir la course."
                elif not par_ve:
                    txt += f" Il manque environ {math.ceil(manque * conso + 0.5)} litres pour finir."
                else:
                    txt += f" Il manque environ {math.ceil(manque)} tours d'énergie pour finir."
            self._dire(e, txt, INFO, "carburant", vie=25)

    # -------------------------------------------------------------------- pneus
    def _pneus_tour(self, e: Etat) -> None:
        usure = max(pn.usure for pn in e.pneus)
        i = max(range(4), key=lambda k: e.pneus[k].usure)
        for seuil, txt in ((0.9, "Pneus en fin de vie"), (0.75, "Pneus bien usés"), (0.5, "Pneus à mi-usure")):
            if usure >= seuil:
                if seuil not in self.usure_seuils:
                    self.usure_seuils.update(s for s in (0.5, 0.75, 0.9) if s <= seuil)
                    self._dire(e, f"{txt} : {round(usure * 100)} pour cent à l'{ROUES[i]}.",
                               NORMAL if seuil >= 0.75 else INFO, "pneus")
                break
        if usure < 0.2:
            self.usure_seuils.clear()  # pneus neufs
        if e.tours_faits < 2 or self.tour_stand:
            return
        for nom, idx in (("avant", (0, 1)), ("arrière", (2, 3))):
            temp = sum(e.pneus[k].temp for k in idx) / 2
            opt = e.pneus[idx[0]].optimal or 85.0
            if temp > opt + 15:
                self._dire(e, f"Pneus {nom} trop chauds, {round(temp)} degrés.", INFO, "pneus",
                           cle=f"chaud{nom}", attente=150)
            elif temp < min(opt - 30, 55):
                self._dire(e, f"Pneus {nom} froids, {round(temp)} degrés.", INFO, "pneus",
                           cle=f"froid{nom}", attente=150)
