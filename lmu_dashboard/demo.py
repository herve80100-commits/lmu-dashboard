"""Source de démonstration : simule des tours du circuit du Mans sans le jeu.

Chaque tour reçoit de petites variations de pilotage (point de freinage,
vitesse mini, remise des gaz, patinage) pour que l'analyse ait de quoi dire.
"""
import bisect
import math
import random
import time
from typing import List, Optional

from .sample import Sample, WheelSample

TRACK_LENGTH = 13626.0
VMAX = 93.0  # m/s
BRAKE_DECEL = 26.0  # m/s²
STEP = 5.0  # m

# Tracé schématique (coordonnées arbitraires), départ sur la ligne.
POLYLINE = [(170, 48), (235, 36), (262, 34), (278, 46), (296, 62), (318, 58), (336, 66), (346, 84), (392, 158),
            (400, 166), (396, 174), (404, 182), (446, 250), (454, 258), (450, 266), (458, 274), (492, 330),
            (496, 344), (482, 346), (350, 330), (330, 324), (318, 334), (306, 346), (290, 356), (278, 346),
            (220, 290), (200, 262), (176, 256), (160, 232), (138, 222), (120, 196), (110, 160), (100, 120),
            (108, 104), (96, 90), (104, 76), (110, 62), (170, 48)]
# (sommet du tracé, vitesse mini km/h, sens du virage)
CORNERS = [(3, 150, 1), (7, 175, 1), (10, 140, -1), (14, 140, 1), (17, 95, 1), (21, 115, -1), (23, 80, 1),
           (27, 190, -1), (29, 170, 1), (33, 105, -1), (35, 115, 1)]
SECTOR_VERTICES = (11, 24)


def _cumulative(points):
    out = [0.0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        out.append(out[-1] + math.hypot(x1 - x0, y1 - y0))
    return out


_CUM = _cumulative(POLYLINE)
SCALE = TRACK_LENGTH / _CUM[-1]
VERTEX_DIST = [c * SCALE for c in _CUM]


def position(d: float):
    """Coordonnées monde (m) au point d du tour."""
    d = d % TRACK_LENGTH
    i = min(bisect.bisect_right(VERTEX_DIST, d) - 1, len(POLYLINE) - 2)
    span = VERTEX_DIST[i + 1] - VERTEX_DIST[i] or 1.0
    f = (d - VERTEX_DIST[i]) / span
    (x0, y0), (x1, y1) = POLYLINE[i], POLYLINE[i + 1]
    return (x0 + f * (x1 - x0)) * SCALE, (y0 + f * (y1 - y0)) * SCALE


class LapProfile:
    """Un tour simulé, discrétisé tous les 5 m."""

    def __init__(self, rng: random.Random, ideal: bool = False):
        n = int(TRACK_LENGTH / STEP) + 1
        self.d = [i * STEP for i in range(n)]
        apexes = [VERTEX_DIST[v] for v, _, _ in CORNERS]
        params = []
        for _, vmin, side in CORNERS:
            if ideal:
                params.append({"bf": 1.0, "vmin": vmin + 2, "delay": 0.0, "tc": False, "lock": False, "side": side})
                continue
            bf = 1.0 - abs(rng.gauss(0, 0.08))
            params.append({
                "bf": max(0.75, bf),
                "vmin": vmin + max(-9.0, min(5.0, rng.gauss(0, 3.0))),
                "delay": max(0.0, rng.gauss(6, 18)),
                "tc": rng.random() < 0.18,
                "lock": rng.random() < 0.06,
                "side": side,
            })

        limit = [VMAX] * n
        for da, p in zip(apexes, params):
            for i in range(max(0, int((da - 15) / STEP)), min(n, int((da + 15) / STEP) + 1)):
                limit[i] = min(limit[i], p["vmin"] / 3.6)

        def next_corner(d):
            j = bisect.bisect_left(apexes, d)
            return j if j < len(apexes) else None

        def prev_corner(d):
            j = bisect.bisect_right(apexes, d) - 1
            return j if j >= 0 else None

        v = [0.0] * n
        thr = [1.0] * n
        v[0] = 70.0
        for i in range(1, n):
            j = prev_corner(self.d[i])
            in_delay = j is not None and apexes[j] < self.d[i] < apexes[j] + params[j]["delay"]
            if in_delay:
                v[i] = min(limit[i], v[i - 1])
                thr[i] = 0.25
            else:
                acc = 11.0 * (1 - v[i - 1] / VMAX) + 0.4
                v[i] = min(limit[i], math.sqrt(v[i - 1] ** 2 + 2 * acc * STEP))
        braking = [False] * n
        for i in range(n - 2, -1, -1):
            j = next_corner(self.d[i])
            decel = BRAKE_DECEL * (params[j]["bf"] if j is not None else 1.0)
            vb = math.sqrt(v[i + 1] ** 2 + 2 * decel * STEP)
            if vb < v[i]:
                v[i] = vb
                braking[i] = True

        brk = [0.0] * n
        i = 0
        while i < n:
            if not braking[i]:
                i += 1
                continue
            k = i
            while k < n and braking[k]:
                k += 1
            j = next_corner(self.d[i])
            peak = 0.95 * (params[j]["bf"] if j is not None else 1.0)
            length = k - i
            for m in range(i, k):
                prog = (m - i) / max(1, length)
                brk[m] = peak if prog < 0.55 else peak * max(0.2, 1 - (prog - 0.55) / 0.45 * 0.8)
                thr[m] = 0.0
            i = k

        thr_f = list(thr)
        slip_front = [0.0] * n
        slip_rear = [0.0] * n
        steer = [0.0] * n
        for da, p in zip(apexes, params):
            a = int(da / STEP)
            for m in range(max(0, a - 8), min(n, a + 9)):
                steer[m] = 0.35 * p["side"]
            if p["tc"]:
                for m in range(a, min(n, a + 24)):
                    if thr[m] > 0.3:
                        thr_f[m] = thr[m] * 0.8
                        slip_rear[m] = 0.16
            if p["lock"]:
                start = next((m for m in range(max(0, a - 120), a) if brk[m] > 0.5), None)
                if start is not None:
                    for m in range(start, min(n, start + 3)):
                        slip_front[m] = -0.3

        t = [0.0] * n
        for i in range(1, n):
            t[i] = t[i - 1] + STEP / max(1.0, (v[i] + v[i - 1]) / 2)
        self.v, self.thr, self.thr_f, self.brk, self.steer = v, thr, thr_f, brk, steer
        self.slip_front, self.slip_rear, self.t = slip_front, slip_rear, t
        self.time = t[-1]
        s1 = t[int(VERTEX_DIST[SECTOR_VERTICES[0]] / STEP)]
        s12 = t[int(VERTEX_DIST[SECTOR_VERTICES[1]] / STEP)]
        self.sectors = (s1, s12 - s1, self.time - s12)


class DemoSource:
    name = "demo"

    def __init__(self, speed: float = 1.0, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.speed = speed
        self.laps: List[LapProfile] = []
        self.starts: List[float] = []
        ideal = LapProfile(self.rng, ideal=True)
        self.rival = tuple(s + 0.12 for s in ideal.sectors)
        self.offset = 0.0
        self.t0 = time.monotonic()

    def _lap_at(self, t: float) -> int:
        while not self.starts or self.starts[-1] + self.laps[-1].time <= t:
            start = self.starts[-1] + self.laps[-1].time if self.laps else 0.0
            self.laps.append(LapProfile(self.rng))
            self.starts.append(start)
        return bisect.bisect_right(self.starts, t) - 1

    def sample_at(self, t: float) -> Sample:
        k = self._lap_at(t)
        lap, lt = self.laps[k], t - self.starts[k]
        i = max(1, min(bisect.bisect_left(lap.t, lt), len(lap.t) - 1))
        f = (lt - lap.t[i - 1]) / max(1e-6, lap.t[i] - lap.t[i - 1])
        lerp = lambda arr: arr[i - 1] + f * (arr[i] - arr[i - 1])  # noqa: E731
        d = lerp(lap.d)
        x, z = position(d)
        v = lerp(lap.v)
        kmh = v * 3.6

        s = Sample(track="Circuit des 24 Heures du Mans", track_length=TRACK_LENGTH, vehicle="Porsche 963 #6",
                   vehicle_class="Hypercar", driver="Vous", session_type="Course",
                   time_remaining=max(0.0, 6 * 3600 - 2400 - t), track_temp=34, air_temp=24)
        s.laps_completed = k
        s.lap_dist = d
        s.lap_time = lt
        s.sector = 1 if d < VERTEX_DIST[SECTOR_VERTICES[0]] else 2 if d < VERTEX_DIST[SECTOR_VERTICES[1]] else 3
        done = self.laps[:k]
        if done:
            prev = done[-1]
            s.last_lap = prev.time
            s.best_lap = min(l.time for l in done)
            s.last_s1, s.last_s2 = prev.sectors[0], prev.sectors[0] + prev.sectors[1]
            s.session_best_sectors = tuple(min([self.rival[j]] + [l.sectors[j] for l in done]) for j in range(3))
        else:
            s.session_best_sectors = self.rival

        s.speed = v
        s.gear = max(1, min(7, 1 + int(kmh / 46)))
        s.rpm = 4200 + (kmh % 46) / 46 * 4500
        s.max_rpm = 8800
        s.throttle, s.throttle_filtered = lerp(lap.thr), lerp(lap.thr_f)
        s.brake, s.steer = lerp(lap.brk), lerp(lap.steer)
        s.brake_bias_front = 54.2
        s.x, s.z = x, z
        s.fuel_capacity = 100.0
        s.fuel = max(0.0, 92.0 - (k + d / TRACK_LENGTH) * 2.95)
        s.compound = "Medium"
        wear = (k % 14 + d / TRACK_LENGTH) * 0.95
        base = (92, 99, 88, 90)
        s.wheels = [WheelSample(temp_c=b + 3 * math.sin(t / 37 + j), pressure_bar=1.76 + j * 0.02,
                                wear_pct=wear * (1.2 if j == 1 else 1.0),
                                slip=lerp(lap.slip_front) if j < 2 else lerp(lap.slip_rear)) for j, b in enumerate(base)]
        for w in s.wheels:
            w.temps_c = (w.temp_c - 2, w.temp_c, w.temp_c + 2)
        s.pitstops = k // 14
        s.position, s.num_cars = 4, 18
        s.gap_ahead, s.ahead_name = round(1.8 + 0.7 * math.sin(t / 90), 3), "#7 Toyota"
        s.gap_behind, s.behind_name = round(2.4 + 0.9 * math.cos(t / 70), 3), "#51 Ferrari"
        return s

    def warmup(self, analyzer, laps: int = 3, hz: float = 20.0) -> None:
        """Rejoue instantanément quelques tours pour que l'analyse soit prête dès l'ouverture."""
        self._lap_at(0)
        while len(self.laps) <= laps:
            self._lap_at(self.starts[-1] + self.laps[-1].time)
        end = self.starts[laps] + 1.0
        t = 0.0
        while t < end:
            analyzer.update(self.sample_at(t))
            t += 1.0 / hz
        self.offset = end
        self.t0 = time.monotonic()

    def read(self) -> Sample:
        return self.sample_at(self.offset + (time.monotonic() - self.t0) * self.speed)
