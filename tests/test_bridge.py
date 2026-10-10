"""Test hors jeu : on remplit une fausse mémoire partagée et on vérifie l'état calculé."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bridge"))
import lmu_shm  # noqa: E402
import lmu_bridge  # noqa: E402


class FakeReader(lmu_shm.LMUReader):
    def __init__(self, buf):
        self._mm = buf


def make_buffer():
    obj = lmu_shm.ObjectOut()
    obj.generic.gameVersion = 1200
    si = obj.scoring.scoringInfo
    si.mTrackName = b"Le Mans"
    si.mSession = 10
    si.mNumVehicles = 3
    si.mGamePhase = 5
    si.mCurrentET = 600.0
    si.mEndET = 3600.0
    si.mMaxLaps = 2147483647
    si.mSectorFlag[1] = 1  # jaune en S2
    for i, (place, cls, player) in enumerate([(1, b"Hypercar", False), (2, b"LMGT3", False), (3, b"Hypercar", True)]):
        v = obj.scoring.vehScoringInfo[i]
        v.mID = i + 10
        v.mPlace = place
        v.mVehicleClass = cls
        v.mIsPlayer = player
    p = obj.scoring.vehScoringInfo[2]
    p.mDriverName = b"Herve"
    p.mSector = 2  # S2
    p.mLapDist = 1500.0
    p.mBestLapTime = 210.5
    p.mBestSector1 = 70.1
    p.mBestSector2 = 140.3
    p.mLastLapTime = 212.0
    p.mCurSector1 = 70.5
    p.mTotalLaps = 5
    tel = obj.telemetry
    tel.playerHasVehicle = True
    tel.playerVehicleIdx = 2
    t = tel.telemInfo[2]
    t.mID = 12
    t.mVehicleName = b"Toyota GR010"
    t.mGear = 4
    t.mEngineRPM = 8000
    t.mEngineMaxRPM = 9000
    t.mLocalVel.z = -50.0  # 180 km/h
    t.mElapsedTime = 650.0
    t.mLapStartET = 600.0
    t.mLapNumber = 6
    t.mFuel = 40.0
    t.mFuelCapacity = 90.0
    t.mVirtualEnergy = 0.55
    t.mDeltaBest = -0.42
    t.mRearBrakeBias = 0.46
    for w, temps in zip(t.mWheels, [(360, 365, 370)] * 4):
        w.mTemperature[0], w.mTemperature[1], w.mTemperature[2] = temps
        w.mPressure = 170
        w.mWear = 0.9
        w.mBrakeTemp = 500
    return bytearray(bytes(obj))


def test_build():
    b = lmu_bridge.Bridge(30)
    b.reader = FakeReader(make_buffer())
    s = b.poll()
    assert s["connected"], s
    assert s["car"]["gear"] == 4
    assert abs(s["car"]["speed"] - 180) < 0.1
    assert s["car"]["brakeBias"] == 54.0
    assert s["lap"]["delta"] == -0.42
    assert s["lap"]["current"] == 50.0
    assert s["lap"]["sector"] == 2
    assert abs(s["lap"]["predicted"] - 210.08) < 1e-6
    assert s["race"]["position"] == 3 and s["race"]["classPosition"] == 2 and s["race"]["classTotal"] == 2
    assert s["race"]["timeLeft"] == 3000 and s["race"]["lapsLeft"] == 15
    assert s["flags"]["yellow"] is True
    fl, fr = s["tyres"][0], s["tyres"][1]
    assert fl["outer"] == round(360 - 273.15, 1) and fl["inner"] == round(370 - 273.15, 1)
    assert fr["outer"] == round(370 - 273.15, 1) and fr["inner"] == round(360 - 273.15, 1)
    assert abs(fl["wear"] - 0.1) < 1e-6
    assert s["fuel"]["ve"] == 0.55


def test_lap_tracker_delta_and_fuel():
    tr = lmu_bridge.LapTracker()
    key = ("t", "c", 10)
    # tour 1 : 100 s pour 1000 m, 3 L
    for i in range(101):
        tr.update(key, 1, i * 1.0, i * 10.0, 50 - i * 0.03, 0.9, False, False, None)
    tr.update(key, 2, 0.0, 0.0, 47.0, 0.88, False, False, 100.0)
    assert tr.fuel_laps == [3.0] and tr.ref_lap_time == 100.0
    # à 500 m en 49 s -> 1 s d'avance
    assert abs(tr.delta(500.0, 49.0) + 1.0) < 1e-9


if __name__ == "__main__":
    test_build()
    test_lap_tracker_delta_and_fuel()
    print("OK")
