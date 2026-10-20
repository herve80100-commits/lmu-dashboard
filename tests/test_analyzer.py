import ctypes as C
import json
import unittest

from lmu_dashboard import rf2_structs as rf2
from lmu_dashboard.analyzer import Analyzer
from lmu_dashboard.demo import CORNERS, DemoSource
from lmu_dashboard.sample import Sample
from lmu_dashboard.shared_memory import parse

TRACK = 2000.0


def lap_samples(laps_completed, speed, start_t, hz=20):
    """Tour synthétique à vitesse constante sur une piste de 2 km."""
    out, t = [], 0.0
    while True:
        d = speed * t
        if d >= TRACK:
            break
        out.append(Sample(track="Test", track_length=TRACK, laps_completed=laps_completed, lap_dist=d, lap_time=t,
                          speed=speed, throttle=1.0, throttle_filtered=1.0, x=d, z=0.0, fuel=50 - laps_completed,
                          fuel_capacity=100))
        t += 1.0 / hz
    return out, TRACK / speed


class AnalyzerTest(unittest.TestCase):
    def test_live_delta_against_best_lap(self):
        a = Analyzer()
        first, t1 = lap_samples(0, 50.0, 0.0)
        for s in first:
            a.update(s)
        second, _ = lap_samples(1, 48.0, t1)
        for s in second[: len(second) // 2]:
            s.last_lap = t1
            a.update(s)
        snap = a.snapshot()
        self.assertAlmostEqual(a.ref_time, t1, places=3)
        self.assertGreater(snap["live"]["delta"], 0)  # plus lent que le meilleur tour
        self.assertAlmostEqual(snap["live"]["predicted"], t1 + snap["live"]["delta"], places=3)

    def test_demo_session_produces_full_analysis(self):
        src = DemoSource(seed=3)
        a = Analyzer()
        src.warmup(a, laps=5)
        snap = json.loads(json.dumps(a.snapshot("demo")))
        self.assertEqual(len(a.corners), len(CORNERS))
        self.assertEqual(snap["laps_done"], 5)
        self.assertIsNotNone(snap["analysis"])
        trace = snap["analysis"]["trace"]
        self.assertAlmostEqual(trace[-1][1], snap["analysis"]["total"], places=3)
        self.assertLessEqual(len(snap["weaknesses"]), 3)
        self.assertTrue(snap["weaknesses"] or snap["strengths"])
        for item in snap["weaknesses"]:
            self.assertGreater(item["delta"], 0)
            self.assertIn(item["category"], ("brake", "traction", "corner"))
        for key in ("brake", "traction", "corner"):
            self.assertTrue(0 <= snap["sections"][key]["score"] <= 100)
        sec = snap["sectors"]
        self.assertAlmostEqual(sum(sec["times"]), a.laps[-1]["time"], places=3)
        self.assertEqual(len(snap["map"]["segments"]), len(CORNERS))

    def test_new_track_resets_reference(self):
        a = Analyzer()
        for s in lap_samples(0, 50.0, 0.0)[0] + lap_samples(1, 50.0, 40.0)[0][:5]:
            a.update(s)
        self.assertIsNotNone(a.ref)
        other = Sample(track="Autre", track_length=3000.0, laps_completed=0, lap_dist=10, speed=40)
        a.update(other)
        self.assertIsNone(a.ref)


class SharedMemoryParseTest(unittest.TestCase):
    def test_player_is_found_and_converted(self):
        sco = rf2.ScoringBuffer()
        sco.mScoringInfo.mTrackName = b"Le Mans"
        sco.mScoringInfo.mLapDist = 13626.0
        sco.mScoringInfo.mNumVehicles = 2
        sco.mScoringInfo.mSession = 10
        rival, me = sco.mVehicles[0], sco.mVehicles[1]
        rival.mID, rival.mPlace, rival.mDriverName = 1, 1, b"Rival"
        rival.mBestLapTime, rival.mBestSector1, rival.mBestSector2, rival.mBestLapSector2 = 205.0, 50.0, 126.0, 126.0
        me.mID, me.mPlace, me.mIsPlayer, me.mTotalLaps, me.mLapDist = 7, 2, True, 4, 1234.0
        me.mTimeBehindNext = 1.5
        me.mLastLapTime, me.mLastSector1, me.mLastSector2 = 206.0, 51.0, 128.0

        tel = rf2.TelemetryBuffer()
        tel.mNumVehicles = 1
        v = tel.mVehicles[0]
        v.mID = 7
        v.mLocalVel.z = -80.0
        v.mUnfilteredThrottle, v.mFilteredThrottle = 1.0, 0.8
        v.mGear, v.mEngineRPM, v.mEngineMaxRPM = 6, 8000, 8800
        v.mFuel, v.mFuelCapacity = 40.0, 100.0
        v.mRearBrakeBias = 0.46
        v.mElapsedTime, v.mLapStartET = 1000.0, 990.0
        for w in v.mWheels:
            w.mTemperature[:] = (363.15, 363.15, 363.15)
            w.mPressure = 180.0
            w.mWear = 0.9

        s = parse(bytes(sco), bytes(tel))
        self.assertIsNotNone(s)
        self.assertEqual(s.track, "Le Mans")
        self.assertEqual(s.session_type, "Course")
        self.assertAlmostEqual(s.speed, 80.0)
        self.assertAlmostEqual(s.lap_time, 10.0)
        self.assertEqual((s.position, s.gap_ahead, s.ahead_name), (2, 1.5, "Rival"))
        self.assertAlmostEqual(s.brake_bias_front, 54.0)
        self.assertAlmostEqual(s.wheels[0].temp_c, 90.0)
        self.assertAlmostEqual(s.wheels[0].pressure_bar, 1.8)
        self.assertAlmostEqual(s.wheels[0].wear_pct, 10.0)
        self.assertEqual(s.session_best_sectors, (50.0, 76.0, 79.0))

    def test_no_player_returns_none(self):
        self.assertIsNone(parse(bytes(rf2.ScoringBuffer()), bytes(rf2.TelemetryBuffer())))

    def test_struct_layout_is_packed_on_4_bytes(self):
        self.assertEqual(rf2.TelemetryBuffer.mVehicles.offset, 16)
        self.assertEqual(rf2.VehicleTelemetry.mDeltaTime.offset, 4)
        self.assertEqual(C.sizeof(rf2.VehicleTelemetry) % 4, 0)


if __name__ == "__main__":
    unittest.main()
