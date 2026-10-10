"""
Pont télémétrie Le Mans Ultimate -> navigateur.

Lit la mémoire partagée native de LMU, calcule les valeurs du dashboard
(delta, consommation, tours restants...) et les diffuse en temps réel
(Server-Sent Events) à la page web, servie elle aussi par ce programme.

Aucune dépendance : Python 3.9+ standard suffit.

    python lmu_bridge.py              -> http://localhost:8080
    python lmu_bridge.py --port 9000 --hz 30
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from lmu_shm import LMUReader, _str

# Dans l'exécutable PyInstaller, les fichiers embarqués sont dans sys._MEIPASS
_BASE = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
WEB_DIR = os.path.join(_BASE, "web")
KELVIN = 273.15

SESSIONS = {0: "Essais libres"}
SESSIONS.update({i: f"Essais {i}" for i in range(1, 5)})
SESSIONS.update({i: f"Qualif {i - 4}" for i in range(5, 9)})
SESSIONS[9] = "Warm-up"
SESSIONS.update({i: "Course" if i == 10 else f"Course {i - 9}" for i in range(10, 14)})


def _num(v, nd=3):
    """Arrondit et remplace les valeurs invalides par None (JSON propre)."""
    if v is None:
        return None
    v = float(v)
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, nd)


def _time(v):
    """Temps au tour : les valeurs <= 0 signifient « pas de temps »."""
    return _num(v) if v and v > 0 else None


class LapTracker:
    """Suit le tour en cours : delta maison, consommation carburant / énergie."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.key = None  # (piste, voiture, session)
        self.lap = None
        self.trace: list[tuple[float, float]] = []  # (distance, temps) du tour en cours
        self.ref_dist: list[float] = []  # meilleur tour : distances
        self.ref_time: list[float] = []  # meilleur tour : temps
        self.ref_lap_time = None
        self.lap_valid = True
        self.lap_in_pits = False
        self.fuel_start = None
        self.ve_start = None
        self.fuel_laps: list[float] = []
        self.ve_laps: list[float] = []

    def update(self, key, lap, lap_time, dist, fuel, ve, invalid, in_pits, last_lap_time):
        if key != self.key:
            self.reset()
            self.key = key
        if lap != self.lap:
            if self.lap is not None and lap == self.lap + 1:
                self._finish_lap(fuel, ve, last_lap_time)
            self.lap = lap
            self.trace = []
            self.lap_valid = True
            self.lap_in_pits = in_pits
            self.fuel_start = fuel
            self.ve_start = ve
        if invalid:
            self.lap_valid = False
        if in_pits:
            self.lap_in_pits = True
        if dist >= 0 and lap_time >= 0 and (not self.trace or dist > self.trace[-1][0]):
            self.trace.append((dist, lap_time))

    def _finish_lap(self, fuel, ve, last_lap_time):
        clean = not self.lap_in_pits
        if clean and self.fuel_start is not None and fuel is not None:
            used = self.fuel_start - fuel
            if used > 0.05:
                self.fuel_laps = (self.fuel_laps + [used])[-5:]
        if clean and self.ve_start is not None and ve is not None:
            used = self.ve_start - ve
            if used > 0.001:
                self.ve_laps = (self.ve_laps + [used])[-5:]
        lap_time = last_lap_time if last_lap_time and last_lap_time > 0 else None
        if (self.lap_valid and clean and lap_time and len(self.trace) > 20
                and (self.ref_lap_time is None or lap_time < self.ref_lap_time)):
            self.ref_lap_time = lap_time
            self.ref_dist = [d for d, _ in self.trace]
            self.ref_time = [t for _, t in self.trace]

    def delta(self, dist, lap_time):
        """Écart avec le meilleur tour à la même distance (interpolation linéaire)."""
        if not self.ref_dist or dist < 0:
            return None
        i = bisect.bisect_left(self.ref_dist, dist)
        if i <= 0:
            ref = self.ref_time[0]
        elif i >= len(self.ref_dist):
            return None
        else:
            d0, d1 = self.ref_dist[i - 1], self.ref_dist[i]
            t0, t1 = self.ref_time[i - 1], self.ref_time[i]
            ref = t0 + (t1 - t0) * ((dist - d0) / (d1 - d0) if d1 > d0 else 0)
        return lap_time - ref

    @staticmethod
    def avg(values):
        return sum(values) / len(values) if values else None


class Bridge:
    def __init__(self, hz: float) -> None:
        self.period = 1.0 / hz
        self.tracker = LapTracker()
        self.reader = None
        self.state = {"connected": False, "source": "lmu", "message": "Démarrage du pont…"}
        self.cond = threading.Condition()
        self.seq = 0

    # --- boucle de lecture -------------------------------------------------
    def run(self) -> None:
        while True:
            start = time.perf_counter()
            try:
                state = self.poll()
            except Exception as exc:  # on ne veut jamais que le pont s'arrête
                state = {"connected": False, "source": "lmu", "message": f"Erreur de lecture : {exc}"}
                self.reader = None
            with self.cond:
                self.state = state
                self.seq += 1
                self.cond.notify_all()
            time.sleep(max(0.0, self.period - (time.perf_counter() - start)))

    def poll(self) -> dict:
        if self.reader is None:
            self.reader = LMUReader()
        snap = self.reader.read()
        if snap is None or snap.version == 0:
            return {"connected": False, "source": "lmu", "message": "En attente de Le Mans Ultimate…"}
        if not snap.has_vehicle or snap.telem is None:
            return {"connected": False, "source": "lmu", "message": "LMU détecté : monte en piste pour voir la télémétrie."}
        return self.build(snap)

    # --- calcul de l'état envoyé à la page ------------------------------------
    def build(self, snap) -> dict:
        t, p, info = snap.telem, snap.player_scoring, snap.info

        speed = math.sqrt(t.mLocalVel.x ** 2 + t.mLocalVel.y ** 2 + t.mLocalVel.z ** 2) * 3.6
        lap_time = t.mElapsedTime - t.mLapStartET
        dist = p.mLapDist
        ve = t.mVirtualEnergy if t.mVirtualEnergy > 0 else None
        in_pits = bool(p.mInPits)
        session = info.mSession

        tr = self.tracker
        tr.update(
            key=(_str(info.mTrackName), _str(t.mVehicleName), session),
            lap=t.mLapNumber, lap_time=lap_time, dist=dist, fuel=t.mFuel, ve=ve,
            invalid=bool(t.mLapInvalidated), in_pits=in_pits, last_lap_time=p.mLastLapTime,
        )

        own_delta = tr.delta(dist, lap_time)
        game_delta = t.mDeltaBest if abs(t.mDeltaBest) > 1e-4 else None
        delta = game_delta if game_delta is not None else own_delta

        best = _time(p.mBestLapTime)
        # Tour estimé = meilleur tour + delta actuel
        predicted = best + delta if best is not None and delta is not None else None

        # Secteurs (mSector : 0=S3, 1=S1, 2=S2)
        sector = {1: 1, 2: 2, 0: 3}.get(p.mSector, 1)
        cur_s1 = _time(p.mCurSector1)
        cur_s2 = _time(p.mCurSector2 - p.mCurSector1) if p.mCurSector2 > 0 and p.mCurSector1 > 0 else None
        best_s1 = _time(p.mBestSector1)
        best_s2 = _time(p.mBestSector2 - p.mBestSector1) if p.mBestSector2 > 0 and p.mBestSector1 > 0 else None
        best_s3 = _time(p.mBestLapTime - p.mBestSector2) if p.mBestLapTime > 0 and p.mBestSector2 > 0 else None

        # Carburant / énergie virtuelle
        fuel_per_lap = tr.avg(tr.fuel_laps)
        ve_per_lap = tr.avg(tr.ve_laps)
        fuel_laps_left = t.mFuel / fuel_per_lap if fuel_per_lap else None
        ve_laps_left = ve / ve_per_lap if ve is not None and ve_per_lap else None

        # Pneus : mTemperature = gauche/centre/droite vu de la voiture.
        # Roues gauches : gauche = extérieur ; roues droites : gauche = intérieur.
        tyres = []
        for i, name in enumerate(("AVG", "AVD", "ARG", "ARD")):
            w = t.mWheels[i]
            left, mid, right = (x - KELVIN for x in w.mTemperature)
            outer, inner = (left, right) if i in (0, 2) else (right, left)
            tyres.append({
                "name": name,
                "inner": _num(inner, 1), "center": _num(mid, 1), "outer": _num(outer, 1),
                "pressure": _num(w.mPressure, 1),
                "wear": _num(1.0 - w.mWear, 4),  # usure : 0 = neuf, 1 = plus de gomme
                "brake": _num(w.mBrakeTemp, 0),
                "optimal": _num(w.mOptimalTemp, 1) if w.mOptimalTemp > 0 else None,
                "flat": bool(w.mFlat), "detached": bool(w.mDetached),
            })

        # Classement général / catégorie
        my_class = p.mVehicleClass
        class_cars = sorted((v for v in snap.vehicles if v.mVehicleClass == my_class), key=lambda v: v.mPlace)
        class_pos = next((i + 1 for i, v in enumerate(class_cars) if v.mIsPlayer), None)

        # Voitures juste devant / derrière dans la catégorie
        def neighbour(v, gap):
            if v is None:
                return None
            return {"name": _str(v.mDriverName), "pos": int(v.mPlace), "gap": _num(gap, 1),
                    "lapsDown": None}
        ahead = behind = None
        if class_pos:
            i = class_pos - 1
            if i > 0:
                a = class_cars[i - 1]
                ahead = neighbour(a, -abs(p.mTimeBehindLeader - a.mTimeBehindLeader))
            if i + 1 < len(class_cars):
                b = class_cars[i + 1]
                behind = neighbour(b, abs(b.mTimeBehindLeader - p.mTimeBehindLeader))

        # Tours / temps restants
        max_laps = info.mMaxLaps if 0 < info.mMaxLaps < 10000 else None
        time_left = info.mEndET - info.mCurrentET if info.mEndET > 0 else None
        if time_left is not None and time_left < 0:
            time_left = 0.0
        laps_left = None
        if max_laps is not None:
            laps_left = max(0, max_laps - p.mTotalLaps)
        elif time_left is not None:
            ref = best or _time(p.mLastLapTime) or _time(p.mEstimatedLapTime)
            if ref:
                laps_left = math.ceil(time_left / ref)

        # Drapeaux
        phase = info.mGamePhase
        sector_idx = (p.mSector + 2) % 3  # S1 -> 0, S2 -> 1, S3 -> 2
        local_yellow = info.mSectorFlag[sector_idx] == 1
        any_yellow = any(f == 1 for f in info.mSectorFlag)
        flags = {
            "phase": phase,
            "green": phase == 5 and not any_yellow,
            "yellow": local_yellow,
            "yellowAhead": any_yellow and not local_yellow,
            "fcy": phase == 6,
            "blue": p.mFlag == 6,
            "red": phase == 7,
            "checkered": phase == 8 or p.mFinishStatus == 1,
            "formation": phase in (3, 4),
            "penalties": int(p.mNumPenalties),
        }

        return {
            "connected": True,
            "source": "lmu",
            "ts": time.time(),
            "track": _str(info.mTrackName),
            "vehicle": _str(t.mVehicleModel) or _str(t.mVehicleName),
            "driver": _str(p.mDriverName),
            "car": {
                "gear": int(t.mGear),
                "maxGears": int(t.mMaxGears),
                "rpm": _num(t.mEngineRPM, 0),
                "maxRpm": _num(t.mEngineMaxRPM, 0),
                "speed": _num(speed, 1),
                "throttle": _num(t.mFilteredThrottle, 3),
                "brake": _num(t.mFilteredBrake, 3),
                "clutch": _num(t.mFilteredClutch, 3),
                "waterTemp": _num(t.mEngineWaterTemp, 1),
                "oilTemp": _num(t.mEngineOilTemp, 1),
                "overheating": bool(t.mOverheating),
                "limiter": bool(t.mSpeedLimiterActive or t.mSpeedLimiter),
                "tc": int(t.mTC), "tcMax": int(t.mTCMax),
                "abs": int(t.mABS), "absMax": int(t.mABSMax),
                "tcCut": int(t.mTCCut), "tcCutMax": int(t.mTCCutMax),
                "tcSlip": int(t.mTCSlip), "tcSlipMax": int(t.mTCSlipMax),
                "motorMap": int(t.mMotorMap), "motorMapMax": int(t.mMotorMapMax),
                "brakeBias": _num((1.0 - t.mRearBrakeBias) * 100, 1),
                "battery": _num(t.mBatteryChargeFraction, 3) if t.mBatteryChargeFraction > 0 else None,
                "damage": sum(t.mDentSeverity),
                "detached": bool(t.mDetached),
            },
            "lap": {
                "number": int(t.mLapNumber),
                "current": _num(lap_time),
                "last": _time(p.mLastLapTime),
                "best": best,
                "delta": _num(delta),
                "predicted": _num(predicted),
                "invalid": bool(t.mLapInvalidated),
                "sector": sector,
                "curS1": cur_s1, "curS2": cur_s2,
                "bestS1": best_s1, "bestS2": best_s2, "bestS3": best_s3,
            },
            "fuel": {
                "level": _num(t.mFuel, 2),
                "capacity": _num(t.mFuelCapacity, 1),
                "perLap": _num(fuel_per_lap, 2),
                "lapsLeft": _num(fuel_laps_left, 1),
                "ve": _num(ve, 4),
                "vePerLap": _num(ve_per_lap, 4),
                "veLapsLeft": _num(ve_laps_left, 1),
            },
            "tyres": tyres,
            "race": {
                "session": SESSIONS.get(session, "Session"),
                "isRace": 10 <= session <= 13,
                "position": int(p.mPlace),
                "total": len(snap.vehicles),
                "classPosition": class_pos,
                "classTotal": len(class_cars),
                "className": _str(my_class),
                "lapsDone": int(p.mTotalLaps),
                "maxLaps": max_laps,
                "lapsLeft": laps_left,
                "timeLeft": _num(time_left, 0),
                "elapsed": _num(info.mCurrentET, 0),
                "gapAhead": _num(t.mTimeGapPlaceAhead, 2) if t.mTimeGapPlaceAhead > 0 else None,
                "gapBehind": _num(t.mTimeGapPlaceBehind, 2) if t.mTimeGapPlaceBehind > 0 else None,
                "pitstops": int(p.mNumPitstops),
                "ahead": ahead, "behind": behind,
                "timeOfDay": _num(info.mTimeOfDay, 0),
                "trackLimits": int(t.mTrackLimitsSteps),
                "inPits": in_pits,
            },
            "flags": flags,
            "weather": {
                "air": _num(info.mAmbientTemp, 1),
                "track": _num(info.mTrackTemp, 1),
                "rain": _num(info.mRaining, 2),
                "wet": _num(info.mAvgPathWetness, 2),
            },
        }

    # --- diffusion --------------------------------------------------------
    def wait(self, last_seq: int, timeout: float = 1.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout=timeout)
            return self.seq, self.state


def make_handler(bridge: Bridge):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=WEB_DIR, **kw)

        def log_message(self, fmt, *args):  # console silencieuse
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        def do_GET(self):
            if self.path.startswith("/stream"):
                return self.stream()
            if self.path.startswith("/api/state"):
                body = json.dumps(bridge.state).encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return None
            return super().do_GET()

        def stream(self):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            seq = -1
            try:
                while True:
                    seq, state = bridge.wait(seq)
                    self.wfile.write(b"data: " + json.dumps(state, separators=(",", ":")).encode() + b"\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description="Pont télémétrie LMU -> navigateur")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = visible aussi depuis une tablette du réseau local")
    ap.add_argument("--hz", type=float, default=30.0, help="fréquence de rafraîchissement")
    ap.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    args = ap.parse_args()

    bridge = Bridge(args.hz)
    threading.Thread(target=bridge.run, daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(bridge))
    server.daemon_threads = True
    url = f"http://localhost:{args.port}"
    print(f"Dashboard LMU prêt : {url}   (Ctrl+C pour arrêter)")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()
