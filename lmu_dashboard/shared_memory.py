"""Lecture de la télémétrie Le Mans Ultimate via la mémoire partagée rFactor 2 (Windows)."""
import ctypes as C
import sys
from typing import Optional

from . import rf2_structs as rf2
from .sample import Sample, WheelSample

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


def _sectors(lap: float, s1: float, s12: float):
    if lap <= 0 or s1 <= 0 or s12 <= 0:
        return None
    return (s1, s12 - s1, lap - s12)


def parse(scoring: bytes, telemetry: bytes) -> Optional[Sample]:
    """Construit un Sample à partir des octets bruts des deux buffers."""
    info = rf2.ScoringInfo.from_buffer_copy(scoring, rf2.ScoringBuffer.mScoringInfo.offset)
    n = max(0, min(info.mNumVehicles, rf2.MAX_MAPPED_VEHICLES))
    vehicles = [rf2.VehicleScoring.from_buffer_copy(scoring, _SCO_HEADER + i * _SCO_VEH) for i in range(n)]
    player = next((v for v in vehicles if v.mIsPlayer), None)
    if player is None:
        return None

    n_tel = max(0, min(C.c_int32.from_buffer_copy(telemetry, C.sizeof(rf2.BufferHeader)).value, rf2.MAX_MAPPED_VEHICLES))
    tel = None
    for i in range(n_tel):
        v = rf2.VehicleTelemetry.from_buffer_copy(telemetry, _TEL_HEADER + i * _TEL_VEH)
        if v.mID == player.mID:
            tel = v
            break
    if tel is None:
        return None

    s = Sample()
    s.track = rf2.text(info.mTrackName)
    s.track_length = info.mLapDist
    s.vehicle = rf2.text(player.mVehicleName)
    s.vehicle_class = rf2.text(player.mVehicleClass)
    s.driver = rf2.text(player.mDriverName)
    s.session_type = SESSION_TYPES.get(info.mSession, "Session")
    s.time_remaining = max(0.0, info.mEndET - info.mCurrentET) if info.mEndET > 0 else None
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
    s.compound = rf2.text(tel.mFrontTireCompoundName)

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
    s.num_cars = n
    if player.mPlace > 1 and player.mLapsBehindNext == 0:
        s.gap_ahead = player.mTimeBehindNext
    ahead = next((v for v in vehicles if v.mPlace == player.mPlace - 1), None)
    behind = next((v for v in vehicles if v.mPlace == player.mPlace + 1), None)
    if ahead is not None:
        s.ahead_name = rf2.text(ahead.mDriverName)
    if behind is not None:
        s.behind_name = rf2.text(behind.mDriverName)
        if behind.mLapsBehindNext == 0:
            s.gap_behind = behind.mTimeBehindNext
    return s


class SharedMemorySource:
    """Lit les buffers « $rFactor2SMMP_* » publiés par le plugin dans LMU."""

    name = "shared_memory"

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("La mémoire partagée de LMU n'est accessible que sous Windows (utilise --demo ailleurs).")
        self._tel = None
        self._sco = None

    def _open(self):
        import mmap
        self._tel = mmap.mmap(-1, C.sizeof(rf2.TelemetryBuffer), rf2.TELEMETRY_NAME, access=mmap.ACCESS_READ)
        self._sco = mmap.mmap(-1, C.sizeof(rf2.ScoringBuffer), rf2.SCORING_NAME, access=mmap.ACCESS_READ)

    @staticmethod
    def _read(m, head_size, count_offset, count_size, veh_size):
        """Copie cohérente : relit tant que le jeu écrit pendant la lecture."""
        data = b""
        for _ in range(5):
            m.seek(0)
            head = m.read(head_size)
            n = C.c_int32.from_buffer_copy(head, count_offset).value if count_size else 0
            n = max(0, min(n, rf2.MAX_MAPPED_VEHICLES))
            data = head + m.read(n * veh_size)
            begin, end = C.c_uint32.from_buffer_copy(data, 0).value, C.c_uint32.from_buffer_copy(data, 4).value
            if begin == end:
                break
        return data

    def read(self) -> Optional[Sample]:
        try:
            if self._tel is None:
                self._open()
            sco = self._read(self._sco, _SCO_HEADER, rf2.ScoringBuffer.mScoringInfo.offset + rf2.ScoringInfo.mNumVehicles.offset, 4, _SCO_VEH)
            tel = self._read(self._tel, _TEL_HEADER, C.sizeof(rf2.BufferHeader), 4, _TEL_VEH)
            return parse(sco, tel)
        except (OSError, ValueError):
            self._tel = self._sco = None
            return None
