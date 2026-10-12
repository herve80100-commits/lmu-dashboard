"""Tests du moteur d'annonces (sans le jeu) : python tests/test_ingenieur.py"""

import math
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ingenieur"))

import demo  # noqa: E402
from etat import chrono, secondes  # noqa: E402
from moteur import Moteur  # noqa: E402
from source_lmu import SourceLMU  # noqa: E402


def rejouer_demo():
    m, t, sortie = Moteur(), 0.0, []
    while t < demo.DUREE:
        sortie += [a.texte for a in m.maj(demo.etat(t))]
        t = round(t + 0.05, 2)
    return sortie


def test_demo_couvre_les_annonces():
    textes = "\n".join(rejouer_demo())
    for attendu in ("Feu vert", "Voiture à gauche", "Trois de front", "Dégagé", "Toujours là",
                    "Position gagnée", "Position perdue", "Meilleur tour", "Consommation",
                    "Carburant bas", "Drapeau jaune", "Drapeau bleu", "Limites de piste",
                    "Pénalité !", "Pénalité purgée", "Limiteur", "Sortie des stands",
                    "assez pour finir", "Freins avant trop chauds", "Freins avant froids, 220 degrés", "Freins avant à bonne température", "Pneus avant trop chauds", "Crevaison",
                    "Dernier tour", "Drapeau à damier", "pleuvoir", "moins d'une seconde"):
        assert attendu in textes, attendu


def test_formats():
    assert chrono(102.34) == "1 minute 42 et 3 dixièmes"
    assert chrono(40.0) == "40 secondes"
    assert secondes(0.4) == "4 dixièmes"
    assert secondes(1.83) == "1,8 seconde"
    assert secondes(2.5) == "2,5 secondes"


def _v(x, y, z):
    return NS(x=x, y=y, z=z)


def _voisins(lacet, autre):
    """Voiture du joueur en (0,0,0) tournée de `lacet` autour de l'axe vertical."""
    c, s = math.cos(lacet), math.sin(lacet)
    # lignes de la matrice local -> monde (rotation autour de y)
    ori = [_v(c, 0, s), _v(0, 1, 0), _v(-s, 0, c)]
    tel = NS(mPos=_v(0, 0, 0), mOri=ori, mID=1)
    snap = NS(vehicles=[], positions={1: (0, 0, 0), 2: autre})
    return SourceLMU()._voisins(snap, tel)


def test_spotter_geometrie():
    # tout droit : avant = -z local ; +x local = gauche
    (lat, lon, _), = _voisins(0.0, (2.5, 0, -1.0))
    assert lat > 2 and abs(lon - 1.0) < 1e-9  # à gauche, 1 m devant
    # voiture tournée de 90° : la même voiture voisine doit rester à gauche
    lacet = math.pi / 2
    gauche_monde = (math.cos(lacet) * 2.5, 0, -math.sin(lacet) * 2.5)
    (lat, lon, _), = _voisins(lacet, gauche_monde)
    assert lat > 2 and abs(lon) < 1e-9


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("OK", nom)
