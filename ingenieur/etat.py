"""
État de course simplifié, commun au jeu (mémoire partagée LMU) et au mode démo.

Le moteur d'annonces ne lit que cette structure : il ne sait pas d'où
viennent les données, ce qui permet de le tester sans le jeu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ROUES = ("avant gauche", "avant droit", "arrière gauche", "arrière droit")


@dataclass
class Pneu:
    usure: float = 0.0  # 0 = neuf, 1 = plus de gomme
    temp: float = 80.0  # °C, moyenne intérieur/centre/extérieur
    optimal: float | None = None  # °C conseillé par le jeu
    pression: float = 0.0  # kPa
    frein: float = 300.0  # °C
    crevaison: bool = False
    detache: bool = False


@dataclass
class Etat:
    t: float = 0.0  # horloge en secondes (croissante)
    connecte: bool = False
    cle: tuple = ()  # (piste, voiture, session) : change = nouvelle session
    session: str = "course"  # essais / qualif / warmup / course
    phase: int = 5  # mGamePhase : 3 formation, 4 feux, 5 vert, 6 FCY, 7 arrêt, 8 fini
    fcy: int = 0  # mYellowFlagState (neutralisation)
    secteurs_jaunes: tuple = (False, False, False)  # S1, S2, S3
    sous_jaune: bool = False
    drapeau_bleu: bool = False
    termine: bool = False

    tours_faits: int = 0
    tours_max: int | None = None
    temps_restant: float | None = None  # s
    secteur: int = 1  # 1..3
    dernier_tour: float | None = None
    meilleur_tour: float | None = None
    tour_invalide: bool = False

    au_stand: bool = False
    etat_stand: int = 0  # 0 rien, 1 demandé, 2 entrée, 3 arrêté, 4 sortie
    limiteur: bool = False
    vitesse: float = 0.0  # km/h

    carburant: float = 0.0  # litres
    reservoir: float = 0.0  # litres
    energie: float | None = None  # énergie virtuelle 0..1 (None si non utilisée)

    position: int = 0  # dans la catégorie
    nb_classe: int = 0
    ecart_devant: float | None = None  # s
    ecart_derriere: float | None = None  # s

    penalites: int = 0
    limites_pas: int = 0
    limites_par_penalite: int = 0

    pneus: list = field(default_factory=lambda: [Pneu() for _ in range(4)])
    eau: float = 80.0
    huile: float = 90.0
    surchauffe: bool = False
    degats: int = 0  # somme des niveaux de dégâts carrosserie (0..16)
    pluie: float = 0.0  # 0..1

    # Voitures proches dans le repère du joueur : (latéral m, longitudinal m)
    # latéral > 0 = à gauche ; longitudinal > 0 = devant
    voisins: list = field(default_factory=list)


def nombre(x: float, dec: int = 1) -> str:
    """1.83 -> « 1,8 » (virgule française, lu correctement par la voix)."""
    s = f"{x:.{dec}f}".replace(".", ",")
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def secondes(x: float) -> str:
    x = abs(x)
    if x < 1:
        d = round(x * 10)
        if d == 0:
            return "moins d'un dixième"
        return "un dixième" if d == 1 else f"{d} dixièmes"
    v = nombre(x, 1)
    return f"{v} seconde" if x < 2 else f"{v} secondes"


def chrono(x: float) -> str:
    """102.34 -> « 1 minute 42 et 3 dixièmes »."""
    x = round(x, 1)
    m, s = divmod(x, 60)
    s_ent = int(s)
    d = int(round((s - s_ent) * 10)) % 10
    base = f"{int(m)} minute {s_ent}" if m >= 1 else f"{s_ent} secondes"
    return f"{base} et {d} dixièmes" if d else base


def place(p: int) -> str:
    return "en tête" if p == 1 else f"en position {p}"
