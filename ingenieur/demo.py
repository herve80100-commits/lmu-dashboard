"""
Mode démo : une course LMP2 de 8 tours rejouée en accéléré (tours de ~40 s)
pour entendre toutes les annonces sans lancer le jeu.
"""

from __future__ import annotations

import bisect

from etat import Etat, Pneu

DEPART = 12.0  # feu vert
TOURS = [42.8, 40.6, 40.9, 40.2, 41.1, 52.0, 40.4, 40.5]
FINS = []
_acc = DEPART
for _x in TOURS:
    _acc += _x
    FINS.append(_acc)
DUREE = FINS[-1] + 12.0
CONSO = 3.6  # litres par tour


def _lin(t, t0, t1, a, b):
    if t <= t0:
        return a
    if t >= t1:
        return b
    return a + (b - a) * (t - t0) / (t1 - t0)


def _debut(n):  # début du tour n (1 = premier tour)
    return DEPART if n == 1 else FINS[n - 2]


# Voitures qui passent à côté : (début, fin, latéral, longitudinal début, fin)
PASSAGES = [
    (_debut(1) + 6, _debut(1) + 11, 2.6, -6.0, 6.5),     # dépassé par la gauche
    (_debut(1) + 7, _debut(1) + 9.2, -2.7, -5.5, 5.0),   # trois de front
    (_debut(1) + 12, _debut(1) + 15, -2.8, 4.0, -6.5),   # on dépasse par la droite
    (_debut(3) + 27, _debut(3) + 31, 2.7, 4.0, -6.5),    # on dépasse par la gauche
    (_debut(4) + 20, _debut(4) + 22, 3.0, -7.0, 7.0),    # hypercar qui prend un tour
    (_debut(7) + 12, _debut(7) + 22, -2.6, 4.5, -6.0),   # long côte à côte (« toujours là »)
]


def _position(t):
    pos = 6
    for quand, p in ((_debut(1) + 14, 5), (_debut(3) + 30, 4), (_debut(6) + 8, 6), (_debut(7) + 21, 5)):
        if t >= quand:
            pos = p
    return pos


def etat(t: float) -> Etat:
    e = Etat(t=t, connecte=True, cle=("Démo Le Mans", "Oreca 07 LMP2", 10), session="course",
             tours_max=len(TOURS), nb_classe=8, reservoir=75.0)
    # phases
    if t < 1:
        e.phase = 0
    elif t < 8:
        e.phase = 3
    elif t < DEPART:
        e.phase = 4
    elif t < FINS[-1]:
        e.phase = 5
    else:
        e.phase = 8
        e.termine = True

    n = bisect.bisect_right(FINS, t)  # tours terminés
    e.tours_faits = n
    if n:
        e.dernier_tour = TOURS[n - 1]
        e.meilleur_tour = min(TOURS[:n])
    tour = min(n + 1, len(TOURS))
    t_tour = t - _debut(tour) if t >= DEPART else 0.0
    frac = max(0.0, min(0.999, t_tour / TOURS[tour - 1]))
    e.secteur = 1 + int(frac * 3)

    e.vitesse = 0.0 if e.phase in (0, 4, 8) else (120.0 if e.phase == 3 else 215.0)
    e.position = _position(t)

    # écarts devant / derrière (interpolés par tour)
    devant = [2.6, 1.9, 1.1, 2.4, 2.1, 1.5, 3.0, 2.2, 1.6]
    derriere = [1.9, 1.7, 1.4, 0.8, 1.3, 1.6, 2.0, 1.5, 1.4]
    i = min(n, len(devant) - 2)
    e.ecart_devant = round(_lin(frac, 0, 1, devant[i], devant[i + 1]), 2)
    e.ecart_derriere = round(_lin(frac, 0, 1, derriere[i], derriere[i + 1]), 2)

    # stands : demande au tour 5, entrée en fin de tour 5, arrêt au tour 6
    d5, d6 = _debut(5), _debut(6)
    if d5 + 8 <= t < FINS[4] - 4:
        e.etat_stand = 1
    elif FINS[4] - 4 <= t < d6 + 3:
        e.etat_stand, e.au_stand = 2, True
        e.vitesse = 85.0 if t < FINS[4] - 2.5 else 60.0
        e.limiteur = t >= FINS[4] - 2.5
    elif d6 + 3 <= t < d6 + 15:
        e.etat_stand, e.au_stand, e.vitesse, e.limiteur = 3, True, 0.0, True
    elif d6 + 15 <= t < d6 + 22:
        e.etat_stand, e.au_stand, e.vitesse, e.limiteur = 4, True, 60.0, True

    # carburant : 22 L au départ, plein à 30 L pendant l'arrêt
    if t < d6 + 3:
        e.carburant = 22.0 - CONSO * (n + frac) if t >= DEPART else 22.0
    else:
        plein = _lin(t, d6 + 3, d6 + 13, 22.0 - CONSO * 5, 30.0)
        tours_apres = max(0.0, (n + frac) - 6.0) if t >= d6 + 15 else 0.0
        e.carburant = plein - CONSO * tours_apres
    e.carburant = max(0.2, e.carburant)

    # drapeaux / pénalités / limites de piste
    d3, d4 = _debut(3), _debut(4)
    e.secteurs_jaunes = (False, d3 + 3 <= t < d3 + 22, False)
    e.sous_jaune = d3 + 14 <= t < d3 + 21
    e.drapeau_bleu = d4 + 18 <= t < d4 + 23
    e.limites_par_penalite = 4
    e.limites_pas = (1 if t >= d3 + 25 else 0) + (1 if t >= d4 + 10 else 0)
    e.penalites = 1 if d5 + 3 <= t < d6 + 10 else 0
    e.pluie = 0.25 if d4 + 5 <= t < _debut(7) else 0.0

    # pneus : usure 10 %/tour, avants trop chauds au tour 5, crevaison au dernier tour
    usure = 0.1 * (n + frac) if t >= DEPART else 0.0
    chaud = 104.0 if d5 <= t < FINS[4] else 86.0
    freins = 1060.0 if d5 + 15 <= t < d5 + 20 else 650.0
    e.pneus = [
        Pneu(usure=usure, temp=chaud, optimal=85.0, pression=170, frein=freins),
        Pneu(usure=usure * 0.95, temp=chaud, optimal=85.0, pression=170, frein=freins),
        Pneu(usure=usure * 0.9, temp=84.0, optimal=85.0, pression=165, frein=600.0),
        Pneu(usure=usure * 0.92, temp=84.0, optimal=85.0, pression=165, frein=600.0,
             crevaison=_debut(8) + 18 <= t < FINS[-1]),
    ]
    e.degats = 1 if t >= _debut(7) + 30 else 0

    # spotter
    for t0, t1, lat, l0, l1 in PASSAGES:
        if t0 <= t <= t1:
            e.voisins.append((lat, _lin(t, t0, t1, l0, l1)))
    return e


__all__ = ["etat", "DUREE"]
