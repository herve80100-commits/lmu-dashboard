"""
Conversion de la mémoire partagée de Le Mans Ultimate vers l'état de course
lu par le moteur d'annonces.
"""

from __future__ import annotations

import math
import time

from etat import Etat, Pneu
from lmu_shm import LMUReader, _str

KELVIN = 273.15


def _session(code: int) -> str:
    if code <= 4:
        return "essais"
    if code <= 8:
        return "qualif"
    if code == 9:
        return "warmup"
    return "course"


class SourceLMU:
    def __init__(self, inverser_cotes: bool = False) -> None:
        self.reader = None
        self.inverser = inverser_cotes
        self.message = "En attente de Le Mans Ultimate…"

    def lire(self) -> Etat:
        t = time.monotonic()
        try:
            if self.reader is None:
                self.reader = LMUReader()
            snap = self.reader.read()
        except Exception as exc:  # jeu fermé, mémoire indisponible…
            self.reader = None
            self.message = f"Mémoire LMU indisponible : {exc}"
            return Etat(t=t)
        if snap is None or snap.version == 0:
            self.message = "En attente de Le Mans Ultimate…"
            return Etat(t=t)
        p = snap.player_scoring
        # Muet tant que le joueur n'est pas au volant en piste (menus, garage, replay, moniteur)
        if (not snap.has_vehicle or snap.telem is None or p is None or not snap.info.mInRealtime
                or p.mInGarageStall or p.mControl != 0):
            self.message = "LMU détecté : monte en piste."
            return Etat(t=t)
        self.message = "Connecté à Le Mans Ultimate"
        return self.convertir(snap, t)

    def convertir(self, snap, t: float) -> Etat:
        tel, p, info = snap.telem, snap.player_scoring, snap.info
        e = Etat(t=t, connecte=True)
        e.session = _session(info.mSession)
        e.cle = (_str(info.mTrackName), _str(tel.mVehicleName), info.mSession)
        e.phase = int(info.mGamePhase)
        e.fcy = int(info.mYellowFlagState)
        # mSectorFlag : index 1 = S1, 2 = S2, 0 = S3 (même convention que mSector)
        sf = [bool(info.mSectorFlag[i]) for i in (1, 2, 0)]
        e.secteurs_jaunes = tuple(sf) if not all(sf) else (False, False, False)
        e.sous_jaune = bool(p.mUnderYellow) and e.phase == 5
        e.drapeau_bleu = p.mFlag == 6
        e.termine = p.mFinishStatus == 1 or e.phase == 8

        e.tours_faits = int(p.mTotalLaps)
        e.tours_max = info.mMaxLaps if 0 < info.mMaxLaps < 10000 else None
        if info.mEndET > 0 and e.tours_max is None:
            e.temps_restant = max(0.0, info.mEndET - info.mCurrentET)
        e.secteur = {1: 1, 2: 2, 0: 3}.get(p.mSector, 1)
        e.dernier_tour = p.mLastLapTime if p.mLastLapTime > 0 else None
        e.meilleur_tour = p.mBestLapTime if p.mBestLapTime > 0 else None
        e.tour_invalide = bool(tel.mLapInvalidated)

        e.au_stand = bool(p.mInPits)
        e.etat_stand = int(p.mPitState)
        e.limiteur = bool(tel.mSpeedLimiterActive)
        v = tel.mLocalVel
        e.vitesse = math.sqrt(v.x ** 2 + v.y ** 2 + v.z ** 2) * 3.6

        e.carburant = float(tel.mFuel)
        e.reservoir = float(tel.mFuelCapacity)
        ve = float(tel.mVirtualEnergy)
        e.energie = (ve if ve <= 1.0 else ve / 100.0) if ve > 0 else None

        # Classement dans la catégorie du joueur
        cls = p.mVehicleClass
        voitures = sorted((x for x in snap.vehicles if x.mVehicleClass == cls), key=lambda x: x.mPlace)
        e.nb_classe = len(voitures)
        e.position_generale = int(p.mPlace)
        e.nb_total = len(snap.vehicles)
        if p.mLastLapTime > 0 and p.mLastSector2 > p.mLastSector1 > 0:
            e.secteurs = (p.mLastSector1, p.mLastSector2 - p.mLastSector1, p.mLastLapTime - p.mLastSector2)
        idx = next((i for i, x in enumerate(voitures) if x.mIsPlayer), None)
        if idx is not None:
            e.position = idx + 1
            if idx > 0:
                a = voitures[idx - 1]
                if a.mLapsBehindLeader == p.mLapsBehindLeader:
                    e.ecart_devant = abs(p.mTimeBehindLeader - a.mTimeBehindLeader)
            if idx + 1 < len(voitures):
                b = voitures[idx + 1]
                if b.mLapsBehindLeader == p.mLapsBehindLeader:
                    e.ecart_derriere = abs(b.mTimeBehindLeader - p.mTimeBehindLeader)

        e.penalites = int(p.mNumPenalties)
        e.limites_pas = int(tel.mTrackLimitsSteps)
        e.limites_par_penalite = int(info.mTrackLimitsStepsPerPenalty)

        e.pneus = []
        for w in tel.mWheels:
            # température « cœur » (comme l'affichage du jeu), la surface refroidit trop vite
            coeur = [x - KELVIN for x in w.mTireInnerLayerTemperature]
            temps = coeur if min(coeur) > -100 and max(coeur) > 0 else [x - KELVIN for x in w.mTemperature]
            e.pneus.append(Pneu(
                usure=max(0.0, min(1.0, 1.0 - w.mWear)),
                temp=sum(temps) / 3,
                optimal=float(w.mOptimalTemp) if w.mOptimalTemp > 0 else None,
                pression=float(w.mPressure),
                frein=float(w.mBrakeTemp),
                crevaison=bool(w.mFlat),
                detache=bool(w.mDetached),
            ))
        e.eau = float(tel.mEngineWaterTemp)
        e.huile = float(tel.mEngineOilTemp)
        e.surchauffe = bool(tel.mOverheating)
        e.degats = int(sum(tel.mDentSeverity))
        e.pluie = float(info.mRaining)
        e.temp_piste = float(info.mTrackTemp)
        e.temp_air = float(info.mAmbientTemp)

        e.voisins = self._voisins(snap, tel)
        lent, bleu = self._trafic(snap, p, e.vitesse, e.session)
        e.sous_jaune = e.sous_jaune or (lent and e.phase == 5)
        e.drapeau_bleu = e.drapeau_bleu or bleu
        return e

    @staticmethod
    def _trafic(snap, p, vitesse, session):
        """Voiture lente/arrêtée devant (jaune) et voiture plus rapide qui arrive (bleu)."""
        long_piste = snap.info.mLapDist
        if long_piste <= 0:
            return False, False
        lent = bleu = False
        for v in snap.vehicles:
            if v.mIsPlayer or v.mInPits or v.mFinishStatus:
                continue
            vv = v.mLocalVel
            kmh = math.sqrt(vv.x ** 2 + vv.y ** 2 + vv.z ** 2) * 3.6
            d = (v.mLapDist - p.mLapDist) % long_piste  # distance devant
            if 0 < d < 350 and kmh < 50 and vitesse > 60:
                lent = True
            derriere = long_piste - d
            if 0 < derriere < 60 and kmh > vitesse + 5:
                autre_classe = v.mVehicleClass != p.mVehicleClass
                prend_tour = session == "course" and v.mTotalLaps > p.mTotalLaps
                if autre_classe or prend_tour:
                    bleu = True
        return lent, bleu

    def _voisins(self, snap, tel) -> list:
        """Position des autres voitures dans le repère de la voiture du joueur.

        rFactor 2 / LMU : +x sort par la gauche, +y par le toit, +z par l'arrière ;
        mOri contient les lignes de la matrice local -> monde.
        """
        px, py, pz = tel.mPos.x, tel.mPos.y, tel.mPos.z
        o = tel.mOri
        # colonnes 0 (axe latéral) et 2 (axe longitudinal) exprimées dans le monde
        ax_x = (o[0].x, o[1].x, o[2].x)
        ax_z = (o[0].z, o[1].z, o[2].z)
        aux_stands = {x.mID for x in snap.vehicles if x.mInPits}
        out = []
        pos = {v.mID: (v.mPos.x, v.mPos.y, v.mPos.z) for v in snap.vehicles}
        pos.update({k: p for k, p in snap.positions.items() if any(p)})
        for vid, (x, y, z) in pos.items():
            if vid == tel.mID or vid in aux_stands:
                continue
            dx, dy, dz = x - px, y - py, z - pz
            if abs(dy) > 4 or dx * dx + dz * dz > 400:
                continue
            lat = dx * ax_x[0] + dy * ax_x[1] + dz * ax_x[2]
            lon = -(dx * ax_z[0] + dy * ax_z[1] + dz * ax_z[2])
            out.append((-lat if self.inverser else lat, lon))
        return out
