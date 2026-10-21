"""Lecture de la télémétrie Le Mans Ultimate (Windows).

Deux interfaces existent :
- « LMU_Data » : la mémoire partagée intégrée au jeu depuis LMU 1.2 (source principale) ;
- les buffers « $rFactor2SMMP_* » du plugin rFactor 2, pour les anciennes versions.
"""
import ctypes as C
import sys
from typing import Optional

from . import rf2_structs as rf2
from .sample import Sample, WheelSample
from .vendor.pyLMUSharedMemory import lmu_data as lmu

SESSION_TYPES = {0: "Essais libres", 9: "Warm-up"}
for _i in range(1, 5):
    SESSION_TYPES[_i] = "Essais"
for _i in range(5, 9):
    SESSION_TYPES[_i] = "Qualification"
for _i in range(10, 14):
    SESSION_TYPES[_i] = "Course"

_TEL_HEADER = rf2.TelemetryBuffer.mVehicles.offset
_TEL_VEH = C.sizeof(rf2.VehicleTelemetry)
_SCO_HEADER = rf2.ScoringBuffer.mVehicles.offset
_SCO_VEH = C.sizeof(rf2.VehicleScoring)


def _text(raw) -> str:
    return rf2.text(bytes(raw))


def _sectors(lap: float, s1: float, s12: float):
    if lap <= 0 or s1 <= 0 or s12 <= 0:
        return None
    return (s1, s12 - s1, lap - s12)


def build_sample(info, vehicles, player, tel) -> Sample:
    """Construit un Sample à partir des structures du jeu (mêmes noms de champs pour LMU et rF2)."""
    s = Sample()
    s.track = _text(info.mTrackName)
    s.track_length = info.mLapDist
    s.vehicle = _text(player.mVehicleName)
    s.vehicle_class = _text(player.mVehicleClass)
    s.driver = _text(player.mDriverName)
    s.session_type = SESSION_TYPES.get(info.mSession, "Session")
    remaining = getattr(info, "mSessionTimeRemaining", 0.0)
    if remaining and remaining > 0:
        s.time_remaining = remaining
    elif info.mEndET > 0:
        s.time_remaining = max(0.0, info.mEndET - info.mCurrentET)
    s.track_temp = info.mTrackTemp
    s.air_temp = info.mAmbientTemp
    s.raining = info.mRaining

    s.laps_completed = player.mTotalLaps
    s.lap_dist = max(0.0, player.mLapDist)
    s.lap_time = max(0.0, tel.mElapsedTime - tel.mLapStartET)
    s.sector = {0: 3, 1: 1, 2: 2}.get(player.mSector, 1)
    s.last_lap = player.mLastLapTime
    s.best_lap = player.mBestLapTime
    s.last_s1 = player.mLastSector1
    s.last_s2 = player.mLastSector2
    s.in_pits = bool(player.mInPits)
    s.pitstops = player.mNumPitstops
    s.lap_invalid = bool(getattr(tel, "mLapInvalidated", False))

    best = [0.0, 0.0, 0.0]
    for v in vehicles:
        sec = _sectors(v.mBestLapTime, v.mBestSector1, v.mBestSector2)
        if sec is None:
            continue
        s3 = v.mBestLapTime - v.mBestLapSector2 if v.mBestLapSector2 > 0 else sec[2]
        for k, val in enumerate((sec[0], sec[1], s3)):
            if val > 0 and (best[k] == 0 or val < best[k]):
                best[k] = val
    s.session_best_sectors = tuple(best)

    vel = tel.mLocalVel
    s.speed = (vel.x ** 2 + vel.y ** 2 + vel.z ** 2) ** 0.5
    s.gear = tel.mGear
    s.rpm = tel.mEngineRPM
    s.max_rpm = tel.mEngineMaxRPM
    s.throttle = tel.mUnfilteredThrottle
    s.throttle_filtered = tel.mFilteredThrottle
    s.brake = tel.mUnfilteredBrake
    s.steer = tel.mUnfilteredSteering
    s.brake_bias_front = (1.0 - tel.mRearBrakeBias) * 100 if 0 < tel.mRearBrakeBias < 1 else 0.0
    s.x = tel.mPos.x
    s.z = tel.mPos.z
    s.fuel = tel.mFuel
    s.fuel_capacity = tel.mFuelCapacity
    s.compound = _text(tel.mFrontTireCompoundName)
    if hasattr(tel, "mTC"):
        s.tc = tel.mTC if tel.mTCMax else None
        s.abs = tel.mABS if tel.mABSMax else None
        s.motor_map = tel.mMotorMap if tel.mMotorMapMax else None
        if 0 < tel.mVirtualEnergy <= 1.0:
            s.virtual_energy = tel.mVirtualEnergy * 100

    wheels = []
    for w in tel.mWheels:
        temps = tuple(t - 273.15 for t in w.mTemperature)
        ground = w.mLongitudinalGroundVel
        slip = w.mLongitudinalPatchVel / ground if abs(ground) > 3 else 0.0
        wheels.append(WheelSample(
            temp_c=sum(temps) / 3,
            temps_c=temps,
            pressure_bar=w.mPressure / 100.0,
            wear_pct=max(0.0, (1.0 - w.mWear) * 100),
            slip=slip,
        ))
    s.wheels = wheels

    s.position = player.mPlace
    s.num_cars = len(vehicles)
    if player.mPlace > 1 and player.mLapsBehindNext == 0:
        s.gap_ahead = player.mTimeBehindNext
    ahead = next((v for v in vehicles if v.mPlace == player.mPlace - 1), None)
    behind = next((v for v in vehicles if v.mPlace == player.mPlace + 1), None)
    if ahead is not None:
        s.ahead_name = _text(ahead.mDriverName)
    if behind is not None:
        s.behind_name = _text(behind.mDriverName)
        if behind.mLapsBehindNext == 0:
            s.gap_behind = behind.mTimeBehindNext
    return s


# ── LMU 1.2+ : mémoire partagée intégrée « LMU_Data » ───────────────────────
def parse_lmu(data: "lmu.LMUObjectOut") -> Optional[Sample]:
    info = data.scoring.scoringInfo
    n = max(0, min(info.mNumVehicles, lmu.LMUConstants.MAX_MAPPED_VEHICLES))
    vehicles = list(data.scoring.vehScoringInfo[:n])
    player = next((v for v in vehicles if v.mIsPlayer), None)
    telemetry = data.telemetry
    if player is None or not telemetry.playerHasVehicle:
        return None
    idx = telemetry.playerVehicleIdx
    tel = telemetry.telemInfo[idx] if idx < lmu.LMUConstants.MAX_MAPPED_VEHICLES else None
    if tel is None or tel.mID != player.mID:
        active = max(0, min(telemetry.activeVehicles, lmu.LMUConstants.MAX_MAPPED_VEHICLES))
        tel = next((t for t in telemetry.telemInfo[:active] if t.mID == player.mID), None)
    if tel is None:
        return None
    return build_sample(info, vehicles, player, tel)


# ── Plugin rFactor 2 (anciennes versions) ──────────────────────────────────
def parse(scoring: bytes, telemetry: bytes) -> Optional[Sample]:
    """Construit un Sample à partir des octets bruts des buffers du plugin rF2."""
    info = rf2.ScoringInfo.from_buffer_copy(scoring, rf2.ScoringBuffer.mScoringInfo.offset)
    n = max(0, min(info.mNumVehicles, rf2.MAX_MAPPED_VEHICLES))
    vehicles = [rf2.VehicleScoring.from_buffer_copy(scoring, _SCO_HEADER + i * _SCO_VEH) for i in range(n)]
    player = next((v for v in vehicles if v.mIsPlayer), None)
    if player is None:
        return None
    n_tel = max(0, min(C.c_int32.from_buffer_copy(telemetry, C.sizeof(rf2.BufferHeader)).value, rf2.MAX_MAPPED_VEHICLES))
    for i in range(n_tel):
        v = rf2.VehicleTelemetry.from_buffer_copy(telemetry, _TEL_HEADER + i * _TEL_VEH)
        if v.mID == player.mID:
            return build_sample(info, vehicles, player, v)
    return None


class SharedMemorySource:
    """Lit LMU_Data (LMU 1.2+), et à défaut les buffers du plugin rFactor 2."""

    name = "shared_memory"

    def __init__(self, verbose: bool = False):
        if sys.platform != "win32":
            raise RuntimeError("La mémoire partagée de LMU n'est accessible que sous Windows (utilise --demo ailleurs).")
        self.verbose = verbose
        self._lmu = None
        self._rf2 = None
        self.interface = None  # "LMU_Data" ou "rFactor2"
        self.status = "en attente du jeu"
        self._last_status = None

    def _log(self, status: str) -> None:
        self.status = status
        if status != self._last_status:
            print(f"[télémétrie] {status}")
            self._last_status = status

    def _read_lmu(self) -> Optional[Sample]:
        import mmap
        if self._lmu is None:
            self._lmu = mmap.mmap(-1, C.sizeof(lmu.LMUObjectOut), lmu.LMUConstants.LMU_SHARED_MEMORY_FILE)
        data = lmu.LMUObjectOut.from_buffer_copy(self._lmu)
        if data.generic.gameVersion == 0 and data.scoring.scoringInfo.mNumVehicles == 0:
            self._log("LMU_Data : pas encore de données (jeu fermé, menu principal ou version < 1.2)")
            return None
        sample = parse_lmu(data)
        if sample is None:
            self._log(f"LMU_Data détectée (version {data.generic.gameVersion}) : monte dans la voiture pour démarrer")
            return None
        self.interface = "LMU_Data"
        self._log(f"Connecté à LMU_Data (version {data.generic.gameVersion}) · {sample.track} · {sample.vehicle}")
        return sample

    def _read_rf2(self) -> Optional[Sample]:
        import mmap
        if self._rf2 is None:
            self._rf2 = (mmap.mmap(-1, C.sizeof(rf2.TelemetryBuffer), rf2.TELEMETRY_NAME),
                         mmap.mmap(-1, C.sizeof(rf2.ScoringBuffer), rf2.SCORING_NAME))
        tel_m, sco_m = self._rf2
        sample = parse(bytes(sco_m), bytes(tel_m))
        if sample is not None:
            self.interface = "rFactor2"
            self._log(f"Connecté au plugin rFactor 2 · {sample.track} · {sample.vehicle}")
        return sample

    def read(self) -> Optional[Sample]:
        for reader in (self._read_lmu, self._read_rf2):
            try:
                sample = reader()
            except (OSError, ValueError) as exc:
                self._log(f"erreur de lecture ({reader.__name__}) : {exc}")
                if reader is self._read_lmu:
                    self._lmu = None
                else:
                    self._rf2 = None
                continue
            if sample is not None:
                return sample
        return None
