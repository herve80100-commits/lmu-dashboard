"""Moteur d'analyse : compare chaque tour au meilleur tour, mètre par mètre.

Le tour est découpé en tranches de 10 m. Pour chaque tranche on garde le temps
de passage, la vitesse et les pédales, ce qui permet de calculer le delta en
direct, de repérer les virages (zones de freinage du meilleur tour) et de dire
où, et pourquoi, du temps a été gagné ou perdu.
"""
import math
import statistics
from typing import Dict, List, Optional

from .sample import Sample

BIN = 10.0  # m
NAN = float("nan")
MAP_STEP = 5  # un point de carte toutes les 5 tranches (50 m)


def _ok(v: float) -> bool:
    return v == v


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _mean(values, default=0.0):
    values = list(values)
    return sum(values) / len(values) if values else default


def _status(score: float) -> str:
    return "good" if score >= 80 else "warn" if score >= 65 else "bad"


class LapTrace:
    """Un tour échantillonné par tranches de distance."""

    FIELDS = ("t", "v", "thr", "thr_f", "brk", "steer", "x", "z")

    def __init__(self, n: int):
        self.n = n
        for f in self.FIELDS:
            setattr(self, f, [NAN] * n)
        self.filled = 0
        self._last = None  # (tranche, distance, temps, x, z)

    def add(self, s: Sample) -> None:
        d = s.lap_dist
        b = min(int(d // BIN), self.n - 1)
        if self._last is None:
            self._set(b, s, s.lap_time, s.x, s.z)
            self._last = (b, d, s.lap_time, s.x, s.z)
            return
        lb, ld, lt, lx, lz = self._last
        if b <= lb:
            return
        if b - lb > 50:  # saut de plus de 500 m (téléportation, retour au stand)
            self._set(b, s, s.lap_time, s.x, s.z)
        else:
            span = d - ld if d > ld else 1.0
            for k in range(lb + 1, b + 1):
                f = _clamp((k * BIN - ld) / span, 0.0, 1.0)
                self._set(k, s, lt + f * (s.lap_time - lt), lx + f * (s.x - lx), lz + f * (s.z - lz))
        self._last = (b, d, s.lap_time, s.x, s.z)

    def _set(self, k, s, t, x, z):
        if not _ok(self.t[k]):
            self.filled += 1
        self.t[k], self.v[k], self.x[k], self.z[k] = t, s.speed, x, z
        self.thr[k], self.thr_f[k], self.brk[k], self.steer[k] = s.throttle, s.throttle_filtered, s.brake, s.steer

    def coverage(self) -> float:
        return self.filled / self.n if self.n else 0.0

    # Outils de recherche sur une plage de tranches
    def _range(self, a, b):
        return range(max(0, a), min(self.n - 1, b) + 1)

    def first(self, field, a, b, pred):
        arr = getattr(self, field)
        return next((k for k in self._range(a, b) if _ok(arr[k]) and pred(arr[k])), None)

    def extreme(self, field, a, b, fn):
        vals = [getattr(self, field)[k] for k in self._range(a, b)]
        vals = [v for v in vals if _ok(v)]
        return fn(vals) if vals else None

    def time_where(self, a, b, pred):
        """Temps passé (s) dans les tranches qui vérifient pred(k)."""
        return sum(BIN / max(self.v[k], 1.0) for k in self._range(a, b) if _ok(self.v[k]) and pred(k))


def detect_corners(ref: LapTrace) -> List[Dict]:
    """Repère les virages à partir des zones de freinage du tour de référence."""
    zones, start = [], None
    for k in range(ref.n):
        braking = _ok(ref.brk[k]) and ref.brk[k] > 0.15
        if braking and start is None:
            start = k
        elif not braking and start is not None:
            zones.append([start, k - 1])
            start = None
    if start is not None:
        zones.append([start, ref.n - 1])
    merged = []
    for z in zones:
        if merged and z[0] - merged[-1][1] < 6:
            merged[-1][1] = z[1]
        else:
            merged.append(z)

    corners = []
    for i, (zs, ze) in enumerate(merged):
        peak = ref.extreme("brk", zs, ze, max) or 0.0
        if peak < 0.3 and ze - zs < 2:
            continue
        window = list(ref._range(zs, ze + 25))
        speeds = [(ref.v[k], k) for k in window if _ok(ref.v[k])]
        if not speeds:
            continue
        apex = min(speeds)[1]
        exit_ = ref.first("thr", apex, apex + 40, lambda v: v >= 0.95)
        exit_ = exit_ if exit_ is not None else min(ref.n - 1, apex + 25)
        if i + 1 < len(merged):
            exit_ = min(exit_, merged[i + 1][0] - 6)
        exit_ = max(exit_, apex + 1)
        corners.append({"brake_start": zs, "entry": max(0, zs - 5), "apex": apex, "exit": min(exit_, ref.n - 1)})
    for i, c in enumerate(corners):
        c["name"] = f"Virage {i + 1}"
        c["km"] = round(c["apex"] * BIN / 1000, 2)
    return corners


def compare_corner(cur: LapTrace, ref: LapTrace, c: Dict) -> Optional[Dict]:
    e, a, x, zs = c["entry"], c["apex"], c["exit"], c["brake_start"]
    if not all(_ok(v) for v in (cur.t[e], cur.t[x], ref.t[e], ref.t[x])):
        return None
    dt = (cur.t[x] - cur.t[e]) - (ref.t[x] - ref.t[e])

    def onset(tr):
        return tr.first("brk", e - 10, a, lambda v: v > 0.15)

    def throttle_on(tr):
        return tr.first("thr", a - 5, x + 20, lambda v: v >= 0.9)

    on_c, on_r = onset(cur), onset(ref)
    th_c, th_r = throttle_on(cur), throttle_on(ref)
    peak_c = cur.extreme("brk", e - 10, x, max) or 0.0
    peak_r = ref.extreme("brk", e - 10, x, max) or 0.0
    vmin_c = (cur.extreme("v", zs, x, min) or 0.0) * 3.6
    vmin_r = (ref.extreme("v", zs, x, min) or 0.0) * 3.6
    tc = _mean(max(0.0, cur.thr[k] - cur.thr_f[k]) for k in cur._range(a, x) if _ok(cur.thr[k]) and _ok(cur.thr_f[k]))

    def coast(tr):
        return tr.time_where(e, x, lambda k: tr.thr[k] < 0.05 and tr.brk[k] < 0.05)

    r = {
        "name": c["name"],
        "km": c["km"],
        "delta": round(dt, 3),
        "brake_delta": (on_c - on_r) * BIN if on_c is not None and on_r is not None else 0.0,
        "peak": peak_c,
        "peak_ref": peak_r,
        "vmin_delta": vmin_c - vmin_r,
        "throttle_delta": (th_c - th_r) * BIN if th_c is not None and th_r is not None else 0.0,
        "tc": tc,
        "coast": coast(cur) - coast(ref),
        "trail": cur.time_where(e, x, lambda k: cur.brk[k] > 0.05 and abs(cur.steer[k]) > 0.08),
        "onset_cur": on_c,
        "onset_ref": on_r,
        "apex": a,
    }
    r["category"], tip = _diagnose(r)
    r["tip"] = tip[:1].upper() + tip[1:]
    return r


def _diagnose(r: Dict):
    """Cause principale du gain ou de la perte, et conseil associé."""
    bd, td, vd, tc = r["brake_delta"], r["throttle_delta"], r["vmin_delta"], r["tc"]
    if r["delta"] >= 0:
        sev = {
            "brake": max(0.0, -bd) / 10 + max(0.0, r["peak_ref"] - r["peak"]) * 100 / 8,
            "traction": max(0.0, td) / 15 + tc / 0.03,
            "corner": max(0.0, -vd) / 2,
        }
        cat = max(sev, key=sev.get)
        if cat == "brake":
            parts = []
            if bd <= -5:
                parts.append(f"Freine {abs(bd):.0f} m plus tard")
            if r["peak_ref"] - r["peak"] > 0.05:
                parts.append(f"pression {r['peak'] * 100:.0f} % → vise {r['peak_ref'] * 100:.0f} %")
            return cat, (", ".join(parts) or "Freinage moins efficace que ta référence") + "."
        if cat == "traction":
            parts = []
            if tc > 0.03:
                parts.append("Patinage en sortie : gaz plus progressifs, roues droites")
            if td >= 5:
                parts.append(f"remets les gaz {td:.0f} m plus tôt")
            return cat, (", ".join(parts) or "Sortie de virage moins efficace") + "."
        if vd <= -1:
            return cat, f"V. mini {vd:+.0f} km/h : entrée plus large, garde l'élan."
        return cat, "Passage plus lent : reprends ta trajectoire de référence."
    sev = {"brake": max(0.0, bd) / 10, "traction": max(0.0, -td) / 15, "corner": max(0.0, vd) / 2}
    cat = max(sev, key=sev.get)
    if sev[cat] == 0:
        return "corner", "Passage plus rapide que ta référence."
    if cat == "brake":
        return cat, f"Freinage {bd:.0f} m plus tard, bien maîtrisé."
    if cat == "traction":
        return cat, f"Gaz {abs(td):.0f} m plus tôt en sortie."
    return cat, f"+{vd:.0f} km/h en vitesse mini."


class Analyzer:
    def __init__(self):
        self.reset(0.0, "")

    def reset(self, track_length: float, track: str) -> None:
        self.track = track
        self.track_length = track_length
        self.n = int(math.ceil(track_length / BIN)) + 1 if track_length > 0 else 0
        self.cur: Optional[LapTrace] = None
        self.cur_lap: Optional[int] = None
        self.cur_valid = True
        self.waiting_line = False
        self.ref: Optional[LapTrace] = None
        self.ref_time: Optional[float] = None
        self.ref_lap: Optional[int] = None
        self.ref_sectors = None
        self.corners: List[Dict] = []
        self.laps: List[Dict] = []
        self.best_sectors = [None, None, None]
        self.analysis: Optional[Dict] = None
        self.fuel_used: List[float] = []
        self.lap_start_fuel = None
        self.tyre_laps = 0
        self.pitstops = None
        self.last: Optional[Sample] = None
        self.last_tyres: Optional[List[Dict]] = None
        self.pending: Optional[Dict] = None  # tour terminé, en attente du temps officiel du jeu
        self.prev_last_lap = 0.0
        self.ev = self._new_events()

    @staticmethod
    def _new_events():
        return {"lock": 0, "tc": 0, "spin": 0.0, "full": 0.0, "total": 0.0, "_lock": False, "_tc": False, "_t": None}

    # ── Mise à jour ─────────────────────────────────────────────────────────
    def update(self, s: Sample) -> None:
        if s.track_length <= 0:
            self.last = s
            return
        if abs(s.track_length - self.track_length) > 1 or s.track != self.track:
            self.reset(s.track_length, s.track)
        if self.pitstops is not None and s.pitstops != self.pitstops:
            self.tyre_laps = 0
        self.pitstops = s.pitstops
        if self.cur_lap is None or s.laps_completed != self.cur_lap:
            if self.cur is not None and s.laps_completed == self.cur_lap + 1:
                self._close_lap(s)
            self._start_lap(s)
        # Le jeu publie le temps et les secteurs du tour un peu après le passage de la ligne :
        # on attend qu'ils changent (5 s au plus) avant de clore l'analyse du tour.
        if self.pending is not None and (s.last_lap != self.pending["stale_last"] or s.lap_time > 5.0):
            self._complete(self.pending, s)
            self.pending = None
        if self.waiting_line and s.lap_dist < 0.5 * self.track_length:
            self.waiting_line = False
        if not self.waiting_line:
            self.cur.add(s)
        if s.in_pits or s.lap_invalid:
            self.cur_valid = False
        self._events(s)
        self.prev_last_lap = s.last_lap
        self.last = s

    def _start_lap(self, s: Sample) -> None:
        self.cur = LapTrace(self.n)
        self.cur_lap = s.laps_completed
        self.cur_valid = not s.in_pits
        self.waiting_line = s.lap_dist > 0.5 * self.track_length
        self.lap_start_fuel = self._resource(s)
        self.ev = self._new_events()

    @staticmethod
    def _resource(s: Sample) -> float:
        """Ressource suivie au tour : énergie virtuelle LMU (%) si disponible, sinon carburant (L)."""
        return s.virtual_energy if s.virtual_energy else s.fuel

    def _events(self, s: Sample) -> None:
        ev = self.ev
        dt = s.lap_time - ev["_t"] if ev["_t"] is not None else 0.0
        ev["_t"] = s.lap_time
        if not 0 < dt < 1:
            dt = 0.0
        locked = s.brake > 0.3 and s.speed > 15 and min(w.slip for w in s.wheels[:2]) < -0.2
        cut = s.throttle > 0.3 and s.throttle - s.throttle_filtered > 0.05
        ev["lock"] += locked and not ev["_lock"]
        ev["tc"] += cut and not ev["_tc"]
        ev["_lock"], ev["_tc"] = locked, cut
        if s.throttle > 0.3 and max(w.slip for w in s.wheels[2:]) > 0.12:
            ev["spin"] += dt
        if s.throttle > 0.98:
            ev["full"] += dt
        ev["total"] += dt

    def _close_lap(self, s: Sample) -> None:
        """Mémorise le tour qui vient de se terminer, en attendant son temps officiel."""
        self.pending = {
            "trace": self.cur, "lap_no": self.cur_lap + 1, "valid": self.cur_valid,
            "events": {k: v for k, v in self.ev.items() if not k.startswith("_")},
            "fuel_used": self.lap_start_fuel - self._resource(s) if self.lap_start_fuel is not None else None,
            "capacity": 100.0 if s.virtual_energy else s.fuel_capacity,
            "stale_last": self.prev_last_lap,
        }
        self.tyre_laps += 1

    def _complete(self, p: Dict, s: Sample) -> None:
        trace, lap_no = p["trace"], p["lap_no"]
        official = s.last_lap > 0 and s.last_lap != p["stale_last"]
        lap_time = s.last_lap if official else max((t for t in trace.t if _ok(t)), default=0.0)
        valid = p["valid"] and trace.coverage() >= 0.95 and lap_time > 0
        sectors = None
        if official and 0 < s.last_s1 < s.last_s2 < s.last_lap:
            sectors = (s.last_s1, s.last_s2 - s.last_s1, s.last_lap - s.last_s2)
        used = p["fuel_used"]
        if valid and used is not None and 0 < used < 0.5 * max(p["capacity"], 1):
            self.fuel_used = (self.fuel_used + [used])[-5:]

        entry = {"lap": lap_no, "time": lap_time, "valid": valid, "sectors": sectors, "status": None, "deltas": None,
                 "events": p["events"]}
        if sectors:
            status = []
            for k in range(3):
                sb, pb = s.session_best_sectors[k], self.best_sectors[k]
                if sb > 0 and sectors[k] <= sb + 1e-3:
                    status.append("purple")
                elif valid and (pb is None or sectors[k] < pb):
                    status.append("green")
                else:
                    status.append("yellow")
                if valid and (pb is None or sectors[k] < pb):
                    self.best_sectors[k] = sectors[k]
            entry["status"] = status
            if self.ref_sectors:
                entry["deltas"] = [round(sectors[k] - self.ref_sectors[k], 3) for k in range(3)]
                entry["deltas_ref"] = self.ref_lap

        if valid and self.ref is not None:
            self.analysis = self._analyse(trace, entry)
        self.laps = (self.laps + [entry])[-60:]
        if valid and (self.ref_time is None or lap_time < self.ref_time):
            self.ref, self.ref_time, self.ref_lap, self.ref_sectors = trace, lap_time, lap_no, sectors
            self.corners = detect_corners(trace)

    # ── Analyse d'un tour terminé ───────────────────────────────────────────
    def _analyse(self, cur: LapTrace, entry: Dict) -> Dict:
        ref = self.ref
        results = [r for r in (compare_corner(cur, ref, c) for c in self.corners) if r]

        trace = []
        for k in range(0, self.n, 10):
            if _ok(cur.t[k]) and _ok(ref.t[k]):
                trace.append([round(k * BIN / 1000, 2), round(cur.t[k] - ref.t[k], 3)])
        total = entry["time"] - self.ref_time
        trace.append([round(self.track_length / 1000, 2), round(total, 3)])

        losses = sorted((r for r in results if r["delta"] > 0.02), key=lambda r: -r["delta"])
        gains = sorted((r for r in results if r["delta"] < -0.02), key=lambda r: r["delta"])
        focus = self._focus(cur, ref, losses[0] if losses else (gains[0] if gains else None))

        ev = entry["events"]
        bd = [r["brake_delta"] for r in results]
        td = [r["throttle_delta"] for r in results]
        vd = [r["vmin_delta"] for r in results]
        brake_score = 100 - min(35, _mean(max(0.0, -v) for v in bd) * 1.2) \
            - min(30, _mean(max(0.0, r["peak_ref"] - r["peak"]) for r in results) * 150) - min(25, ev["lock"] * 6)
        spin_pct = ev["spin"] / ev["total"] * 100 if ev["total"] else 0.0
        traction_score = 100 - min(30, _mean(max(0.0, v) for v in td) * 0.8) - min(30, spin_pct * 5) - min(25, ev["tc"] * 1.5)
        corner_score = 100 - min(60, _mean(max(0.0, -v) for v in vd) * 5)
        best_c = max(results, key=lambda r: r["vmin_delta"]) if results else None
        worst_c = min(results, key=lambda r: r["vmin_delta"]) if results else None

        def section(score, metrics):
            score = round(_clamp(score))
            return {"score": score, "status": _status(score), "metrics": metrics}

        sector_km = []
        if self.ref_sectors:
            for target in (self.ref_sectors[0], self.ref_sectors[0] + self.ref_sectors[1]):
                k = next((k for k in range(self.n) if _ok(ref.t[k]) and ref.t[k] >= target), None)
                if k is not None:
                    sector_km.append(round(k * BIN / 1000, 2))
        return {
            "lap": entry["lap"],
            "ref_lap": self.ref_lap,
            "total": round(total, 3),
            "corners": results,
            "sector_km": sector_km,
            "marks": [{"km": r["km"], "delta": r["delta"], "name": r["name"]} for r in losses[:3] + gains[:2]],
            "trace": trace,
            "focus": focus,
            "weaknesses": [self._item(r) for r in losses[:3]],
            "strengths": [self._item(r) for r in gains[:3]],
            "brake": section(brake_score, [
                ["Point de freinage", f"{_mean(bd):+.0f} m vs réf."],
                ["Pression max moy.", f"{_mean(r['peak'] for r in results) * 100:.0f} %"],
                ["Freinage dégressif", f"{_mean(r['trail'] for r in results):.1f} s / virage"],
                ["Blocages de roue", f"{ev['lock']} / tour"],
            ]),
            "traction": section(traction_score, [
                ["Patinage", f"{spin_pct:.1f} % du tour"],
                ["Remise des gaz", f"{_mean(td):+.0f} m vs réf."],
                ["Coupures antipatinage", f"{ev['tc']} / tour"],
                ["Temps plein gaz", f"{ev['full'] / ev['total'] * 100 if ev['total'] else 0:.0f} %"],
            ]),
            "corner": section(corner_score, [
                ["V. mini moyenne", f"{_mean(vd):+.1f} km/h"],
                ["Meilleur virage", f"{best_c['name']} {best_c['vmin_delta']:+.0f}" if best_c else "—"],
                ["Pire virage", f"{worst_c['name']} {worst_c['vmin_delta']:+.0f}" if worst_c else "—"],
                ["Virages analysés", str(len(results))],
            ]),
        }

    @staticmethod
    def _item(r: Dict) -> Dict:
        return {"name": f"{r['name']} · km {r['km']:.1f}", "category": r["category"], "delta": r["delta"], "tip": r["tip"]}

    def _focus(self, cur: LapTrace, ref: LapTrace, r: Optional[Dict]) -> Optional[Dict]:
        """Courbes frein / gaz autour du virage le plus coûteux."""
        if r is None:
            return None
        a = r["apex"]
        start = (r["onset_ref"] if r["onset_ref"] is not None else a - 20) - 15
        end = a + 25

        def series(tr, field):
            arr = getattr(tr, field)
            return [[round((k - a) * BIN), round(arr[k] * 100)] for k in tr._range(start, end) if _ok(arr[k])]

        notes = []
        if abs(r["brake_delta"]) >= 5:
            notes.append(f"Freinage {abs(r['brake_delta']):.0f} m {'trop tôt' if r['brake_delta'] < 0 else 'plus tard'}")
        notes.append(f"pression {r['peak'] * 100:.0f} % vs {r['peak_ref'] * 100:.0f} %")
        rel = lambda k: round((k - a) * BIN) if k is not None else None  # noqa: E731
        return {
            "name": r["name"],
            "km": r["km"],
            "delta": r["delta"],
            "range": [round((start - a) * BIN), round((end - a) * BIN)],
            "cur": {"brake": series(cur, "brk"), "throttle": series(cur, "thr")},
            "ref": {"brake": series(ref, "brk"), "throttle": series(ref, "thr")},
            "onset_cur": rel(r["onset_cur"]),
            "onset_ref": rel(r["onset_ref"]),
            "headline": " · ".join(notes),
            "coast": round(r["coast"], 2),
            "throttle_delta": round(r["throttle_delta"]),
        }

    # ── Instantané envoyé au dashboard ──────────────────────────────────────
    def _map(self) -> Optional[Dict]:
        src = self.ref or self.cur
        if src is None:
            return None
        idx = [k for k in range(0, self.n, MAP_STEP) if _ok(src.x[k])]
        if len(idx) < 10:
            return None
        xs, zs = [src.x[k] for k in idx], [src.z[k] for k in idx]
        minx, minz = min(xs), min(zs)
        span = max(max(xs) - minx, max(zs) - minz) or 1.0
        ox, oz = (span - (max(xs) - minx)) / 2, (span - (max(zs) - minz)) / 2

        def norm(x, z):
            return [round((x - minx + ox) / span, 4), round((z - minz + oz) / span, 4)]

        pos = {k: i for i, k in enumerate(idx)}

        def nearest(k):
            k = min(max(0, k), self.n - 1)
            best = min(idx, key=lambda j: abs(j - k))
            return pos[best]

        segments = []
        if self.analysis:
            by_name = {r["name"]: r for r in self.analysis["corners"]}
            for c in self.corners:
                r = by_name.get(c["name"])
                if r:
                    segments.append({"from": nearest(c["entry"]), "to": nearest(c["exit"]), "apex": nearest(c["apex"]),
                                     "name": c["name"], "delta": r["delta"]})
        s = self.last
        car = norm(s.x, s.z) if s else None
        sector_marks = []
        if self.ref_sectors and self.ref:
            for target in (self.ref_sectors[0], self.ref_sectors[0] + self.ref_sectors[1]):
                k = next((k for k in idx if src.t[k] >= target), None)
                if k is not None:
                    sector_marks.append(pos[k])
        return {"path": [norm(src.x[k], src.z[k]) for k in idx], "segments": segments, "car": car,
                "sectors": sector_marks, "complete": src is self.ref}

    def snapshot(self, source: str = "") -> Dict:
        s = self.last
        if s is None:
            return {"connected": False, "source": source}
        b = min(int(s.lap_dist // BIN), self.n - 1) if self.n else 0
        delta = None
        if self.ref is not None and self.cur is not None and not self.waiting_line \
                and _ok(self.cur.t[b]) and _ok(self.ref.t[b]):
            delta = round(self.cur.t[b] - self.ref.t[b], 3)
        valid_laps = [l for l in self.laps if l["valid"]]
        last_lap = self.laps[-1] if self.laps else None
        sector_lap = next((l for l in reversed(self.laps) if l["sectors"]), None)
        theoretical = sum(self.best_sectors) if all(self.best_sectors) else None
        if theoretical is not None and self.ref_time is not None:
            theoretical = min(theoretical, self.ref_time)

        stale = False
        if all(w.valid for w in s.wheels):
            wheels = []
            for name, w in zip(("AVG", "AVD", "ARG", "ARD"), s.wheels):
                lo, hi = (w.optimal_c - 15, w.optimal_c + 15) if w.optimal_c else (70, 105)
                state = "cold" if w.temp_c < lo else "hot" if w.temp_c > hi else "ok"
                wheels.append({"pos": name, "temp": round(w.temp_c), "pressure": round(w.pressure_bar, 2),
                               "wear": round(w.wear_pct, 1), "state": state,
                               "surface": round(w.surface_c) if w.surface_c is not None else None,
                               "optimal": round(w.optimal_c) if w.optimal_c else None})
            self.last_tyres = wheels
        else:  # pas de mesure en ce moment : on garde la dernière mesure en piste
            wheels, stale = self.last_tyres, True
        per_lap = _mean(self.fuel_used, None) if self.fuel_used else None
        res = self._resource(s)
        laps_left = res / per_lap if per_lap else None

        if self.ref_time:
            valid_laps = [l for l in valid_laps if l["time"] <= self.ref_time * 1.07]
        times = [l["time"] for l in valid_laps[-10:]]
        consistency = None
        if len(times) >= 3:
            sigma = statistics.pstdev(times)
            score = round(_clamp(100 - sigma * 30))
            consistency = {"score": score, "status": _status(score), "sigma": round(sigma, 3),
                           "spread": round(max(times) - min(times), 3),
                           "laps": [{"lap": l["lap"], "time": l["time"]} for l in valid_laps[-10:]]}

        analysis = self.analysis
        strengths = list(analysis["strengths"]) if analysis else []
        if consistency and consistency["sigma"] < 0.5 and len(times) >= 5:
            strengths = strengths[:2] + [{"name": "Régularité", "category": "consistency", "value": f"σ {consistency['sigma']:.2f} s",
                                          "tip": f"{len(times)} derniers tours dans une fenêtre de {consistency['spread']:.1f} s."}]

        return {
            "connected": True,
            "source": source,
            "session": {
                "track": s.track, "track_km": round(self.track_length / 1000, 3), "vehicle": s.vehicle,
                "vehicle_class": s.vehicle_class, "driver": s.driver, "type": s.session_type,
                "lap": s.laps_completed + 1, "time_remaining": s.time_remaining, "position": s.position,
                "num_cars": s.num_cars, "gap_ahead": s.gap_ahead, "ahead": s.ahead_name, "gap_behind": s.gap_behind,
                "behind": s.behind_name, "track_temp": round(s.track_temp), "air_temp": round(s.air_temp),
                "raining": s.raining > 0.1,
            },
            "live": {
                "lap_time": round(s.lap_time, 3), "delta": delta,
                "predicted": round(self.ref_time + delta, 3) if delta is not None else None,
                "last_lap": last_lap["time"] if last_lap else (s.last_lap or None),
                "best_lap": self.ref_time, "best_lap_no": self.ref_lap, "theoretical": theoretical,
                "speed": round(s.speed * 3.6), "gear": s.gear, "rpm": round(s.rpm), "max_rpm": round(s.max_rpm),
                "throttle": round(s.throttle * 100), "brake": round(s.brake * 100),
                "brake_bias": round(s.brake_bias_front, 1) if s.brake_bias_front else None,
                "tc": s.tc, "abs": s.abs, "motor_map": s.motor_map,
                "in_pits": s.in_pits, "sector": s.sector,
            },
            "sectors": {"lap": sector_lap["lap"], "times": sector_lap["sectors"], "status": sector_lap["status"],
                        "deltas": sector_lap["deltas"], "ref_lap": sector_lap.get("deltas_ref")} if sector_lap else None,
            "map": self._map(),
            "analysis": None if analysis is None else {
                "lap": analysis["lap"], "ref_lap": analysis["ref_lap"], "total": analysis["total"],
                "trace": analysis["trace"], "focus": analysis["focus"],
                "sector_km": analysis["sector_km"], "marks": analysis["marks"],
            },
            "weaknesses": analysis["weaknesses"] if analysis else [],
            "strengths": strengths,
            "sections": {
                "brake": analysis["brake"] if analysis else None,
                "traction": analysis["traction"] if analysis else None,
                "corner": analysis["corner"] if analysis else None,
                "tyres": {"compound": s.compound, "laps": self.tyre_laps, "wheels": wheels, "stale": stale},
                "energy": {"kind": "virtual" if s.virtual_energy else "fuel",
                           "pct": round(s.virtual_energy) if s.virtual_energy else (round(s.fuel / s.fuel_capacity * 100) if s.fuel_capacity else None),
                           "fuel": round(s.fuel, 1), "per_lap": round(per_lap, 2) if per_lap else None,
                           "laps_left": round(laps_left, 1) if laps_left else None,
                           "pit_lap": s.laps_completed + 1 + int(laps_left) if laps_left else None},
                "consistency": consistency,
            },
            "best_lap": self.ref_time,
            "laps_done": len(self.laps),
        }
