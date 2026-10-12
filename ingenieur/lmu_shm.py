"""
Lecture de la mémoire partagée native de Le Mans Ultimate ("LMU_Data").

La structure reproduit l'en-tête officiel de Studio 397
(dossier du jeu : Support\\SharedMemoryInterface\\SharedMemoryInterface.hpp),
d'après la cartographie Python de TinyPedal/pyLMUSharedMemory.
Toutes les structures sont alignées sur 4 octets (#pragma pack(4)).
"""

from __future__ import annotations

import ctypes
import mmap
import sys

SHM_NAME = "LMU_Data"
MAX_VEHICLES = 104
MAX_PATH = 260


class _S(ctypes.Structure):
    _pack_ = 4


class Vect3(_S):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("z", ctypes.c_double)]


class Wheel(_S):
    _fields_ = [
        ("mSuspensionDeflection", ctypes.c_double),
        ("mRideHeight", ctypes.c_double),
        ("mSuspForce", ctypes.c_double),
        ("mBrakeTemp", ctypes.c_double),  # Kelvin dans LMU
        ("mBrakePressure", ctypes.c_double),
        ("mRotation", ctypes.c_double),
        ("mLateralPatchVel", ctypes.c_double),
        ("mLongitudinalPatchVel", ctypes.c_double),
        ("mLateralGroundVel", ctypes.c_double),
        ("mLongitudinalGroundVel", ctypes.c_double),
        ("mCamber", ctypes.c_double),
        ("mLateralForce", ctypes.c_double),
        ("mLongitudinalForce", ctypes.c_double),
        ("mTireLoad", ctypes.c_double),
        ("mGripFract", ctypes.c_double),
        ("mPressure", ctypes.c_double),  # kPa
        ("mTemperature", ctypes.c_double * 3),  # Kelvin, gauche/centre/droite
        ("mWear", ctypes.c_double),  # fraction de gomme restante (1.0 = neuf)
        ("mTerrainName", ctypes.c_char * 16),
        ("mSurfaceType", ctypes.c_ubyte),
        ("mFlat", ctypes.c_bool),
        ("mDetached", ctypes.c_bool),
        ("mStaticUndeflectedRadius", ctypes.c_ubyte),
        ("mVerticalTireDeflection", ctypes.c_double),
        ("mWheelYLocation", ctypes.c_double),
        ("mToe", ctypes.c_double),
        ("mTireCarcassTemperature", ctypes.c_double),
        ("mTireInnerLayerTemperature", ctypes.c_double * 3),
        ("mOptimalTemp", ctypes.c_float),  # °C
        ("mCompoundIndex", ctypes.c_ubyte),
        ("mCompoundType", ctypes.c_ubyte),
        ("mExpansion", ctypes.c_ubyte * 18),
    ]


class VehicleTelemetry(_S):
    _fields_ = [
        ("mID", ctypes.c_int),
        ("mDeltaTime", ctypes.c_double),
        ("mElapsedTime", ctypes.c_double),
        ("mLapNumber", ctypes.c_int),
        ("mLapStartET", ctypes.c_double),
        ("mVehicleName", ctypes.c_char * 64),
        ("mTrackName", ctypes.c_char * 64),
        ("mPos", Vect3),
        ("mLocalVel", Vect3),
        ("mLocalAccel", Vect3),
        ("mOri", Vect3 * 3),
        ("mLocalRot", Vect3),
        ("mLocalRotAccel", Vect3),
        ("mGear", ctypes.c_int),
        ("mEngineRPM", ctypes.c_double),
        ("mEngineWaterTemp", ctypes.c_double),
        ("mEngineOilTemp", ctypes.c_double),
        ("mClutchRPM", ctypes.c_double),
        ("mUnfilteredThrottle", ctypes.c_double),
        ("mUnfilteredBrake", ctypes.c_double),
        ("mUnfilteredSteering", ctypes.c_double),
        ("mUnfilteredClutch", ctypes.c_double),
        ("mFilteredThrottle", ctypes.c_double),
        ("mFilteredBrake", ctypes.c_double),
        ("mFilteredSteering", ctypes.c_double),
        ("mFilteredClutch", ctypes.c_double),
        ("mSteeringShaftTorque", ctypes.c_double),
        ("mFront3rdDeflection", ctypes.c_double),
        ("mRear3rdDeflection", ctypes.c_double),
        ("mFrontWingHeight", ctypes.c_double),
        ("mFrontRideHeight", ctypes.c_double),
        ("mRearRideHeight", ctypes.c_double),
        ("mDrag", ctypes.c_double),
        ("mFrontDownforce", ctypes.c_double),
        ("mRearDownforce", ctypes.c_double),
        ("mFuel", ctypes.c_double),
        ("mEngineMaxRPM", ctypes.c_double),
        ("mScheduledStops", ctypes.c_ubyte),
        ("mOverheating", ctypes.c_bool),
        ("mDetached", ctypes.c_bool),
        ("mHeadlights", ctypes.c_bool),
        ("mDentSeverity", ctypes.c_ubyte * 8),
        ("mLastImpactET", ctypes.c_double),
        ("mLastImpactMagnitude", ctypes.c_double),
        ("mLastImpactPos", Vect3),
        ("mEngineTorque", ctypes.c_double),
        ("mCurrentSector", ctypes.c_int),
        ("mSpeedLimiter", ctypes.c_ubyte),
        ("mMaxGears", ctypes.c_ubyte),
        ("mFrontTireCompoundIndex", ctypes.c_ubyte),
        ("mRearTireCompoundIndex", ctypes.c_ubyte),
        ("mFuelCapacity", ctypes.c_double),
        ("mFrontFlapActivated", ctypes.c_ubyte),
        ("mRearFlapActivated", ctypes.c_ubyte),
        ("mRearFlapLegalStatus", ctypes.c_ubyte),
        ("mIgnitionStarter", ctypes.c_ubyte),
        ("mFrontTireCompoundName", ctypes.c_char * 18),
        ("mRearTireCompoundName", ctypes.c_char * 18),
        ("mSpeedLimiterAvailable", ctypes.c_ubyte),
        ("mAntiStallActivated", ctypes.c_ubyte),
        ("mUnused", ctypes.c_ubyte * 2),
        ("mVisualSteeringWheelRange", ctypes.c_float),
        ("mRearBrakeBias", ctypes.c_double),
        ("mTurboBoostPressure", ctypes.c_double),
        ("mPhysicsToGraphicsOffset", ctypes.c_float * 3),
        ("mPhysicalSteeringWheelRange", ctypes.c_float),
        ("mDeltaBest", ctypes.c_double),
        ("mBatteryChargeFraction", ctypes.c_double),
        ("mElectricBoostMotorTorque", ctypes.c_double),
        ("mElectricBoostMotorRPM", ctypes.c_double),
        ("mElectricBoostMotorTemperature", ctypes.c_double),
        ("mElectricBoostWaterTemperature", ctypes.c_double),
        ("mElectricBoostMotorState", ctypes.c_ubyte),
        ("mLapInvalidated", ctypes.c_bool),
        ("mABSActive", ctypes.c_bool),
        ("mTCActive", ctypes.c_bool),
        ("mSpeedLimiterActive", ctypes.c_bool),
        ("mWiperState", ctypes.c_uint8),
        ("mTC", ctypes.c_uint8),
        ("mTCMax", ctypes.c_uint8),
        ("mTCSlip", ctypes.c_uint8),
        ("mTCSlipMax", ctypes.c_uint8),
        ("mTCCut", ctypes.c_uint8),
        ("mTCCutMax", ctypes.c_uint8),
        ("mABS", ctypes.c_uint8),
        ("mABSMax", ctypes.c_uint8),
        ("mMotorMap", ctypes.c_uint8),
        ("mMotorMapMax", ctypes.c_uint8),
        ("mMigration", ctypes.c_uint8),
        ("mMigrationMax", ctypes.c_uint8),
        ("mFrontAntiSway", ctypes.c_uint8),
        ("mFrontAntiSwayMax", ctypes.c_uint8),
        ("mRearAntiSway", ctypes.c_uint8),
        ("mRearAntiSwayMax", ctypes.c_uint8),
        ("mLiftAndCoastProgress", ctypes.c_uint8),
        ("mTrackLimitsSteps", ctypes.c_uint8),
        ("mRegen", ctypes.c_float),
        ("mStateOfCharge", ctypes.c_float),
        ("mVirtualEnergy", ctypes.c_float),
        ("mTimeGapCarAhead", ctypes.c_float),
        ("mTimeGapCarBehind", ctypes.c_float),
        ("mTimeGapPlaceAhead", ctypes.c_float),
        ("mTimeGapPlaceBehind", ctypes.c_float),
        ("mVehicleModel", ctypes.c_char * 30),
        ("mVehicleClass", ctypes.c_uint8),
        ("mVehicleChampionship", ctypes.c_uint8),
        ("mExpansion", ctypes.c_ubyte * 20),
        ("mWheels", Wheel * 4),  # 0=AVG 1=AVD 2=ARG 3=ARD
    ]


class VehicleScoring(_S):
    _fields_ = [
        ("mID", ctypes.c_int),
        ("mDriverName", ctypes.c_char * 32),
        ("mVehicleName", ctypes.c_char * 64),
        ("mTotalLaps", ctypes.c_short),
        ("mSector", ctypes.c_byte),  # 0=S3 1=S1 2=S2
        ("mFinishStatus", ctypes.c_byte),
        ("mLapDist", ctypes.c_double),
        ("mPathLateral", ctypes.c_double),
        ("mTrackEdge", ctypes.c_double),
        ("mBestSector1", ctypes.c_double),
        ("mBestSector2", ctypes.c_double),
        ("mBestLapTime", ctypes.c_double),
        ("mLastSector1", ctypes.c_double),
        ("mLastSector2", ctypes.c_double),
        ("mLastLapTime", ctypes.c_double),
        ("mCurSector1", ctypes.c_double),
        ("mCurSector2", ctypes.c_double),
        ("mNumPitstops", ctypes.c_short),
        ("mNumPenalties", ctypes.c_short),
        ("mIsPlayer", ctypes.c_bool),
        ("mControl", ctypes.c_byte),
        ("mInPits", ctypes.c_bool),
        ("mPlace", ctypes.c_ubyte),
        ("mVehicleClass", ctypes.c_char * 32),
        ("mTimeBehindNext", ctypes.c_double),
        ("mLapsBehindNext", ctypes.c_int),
        ("mTimeBehindLeader", ctypes.c_double),
        ("mLapsBehindLeader", ctypes.c_int),
        ("mLapStartET", ctypes.c_double),
        ("mPos", Vect3),
        ("mLocalVel", Vect3),
        ("mLocalAccel", Vect3),
        ("mOri", Vect3 * 3),
        ("mLocalRot", Vect3),
        ("mLocalRotAccel", Vect3),
        ("mHeadlights", ctypes.c_ubyte),
        ("mPitState", ctypes.c_ubyte),
        ("mServerScored", ctypes.c_ubyte),
        ("mIndividualPhase", ctypes.c_ubyte),
        ("mQualification", ctypes.c_int),
        ("mTimeIntoLap", ctypes.c_double),
        ("mEstimatedLapTime", ctypes.c_double),
        ("mPitGroup", ctypes.c_char * 24),
        ("mFlag", ctypes.c_ubyte),  # 0=vert 6=bleu
        ("mUnderYellow", ctypes.c_bool),
        ("mCountLapFlag", ctypes.c_ubyte),
        ("mInGarageStall", ctypes.c_bool),
        ("mUpgradePack", ctypes.c_ubyte * 16),
        ("mPitLapDist", ctypes.c_float),
        ("mBestLapSector1", ctypes.c_float),
        ("mBestLapSector2", ctypes.c_float),
        ("mSteamID", ctypes.c_ulonglong),
        ("mVehFilename", ctypes.c_char * 32),
        ("mAttackMode", ctypes.c_short),
        ("mFuelFraction", ctypes.c_ubyte),
        ("mDRSState", ctypes.c_bool),
        ("mExpansion", ctypes.c_ubyte * 4),
    ]


class ScoringInfo(_S):
    _fields_ = [
        ("mTrackName", ctypes.c_char * 64),
        ("mSession", ctypes.c_int),
        ("mCurrentET", ctypes.c_double),
        ("mEndET", ctypes.c_double),
        ("mMaxLaps", ctypes.c_int),
        ("mLapDist", ctypes.c_double),
        ("mResultsStreamPointer", ctypes.c_ubyte * 8),
        ("mNumVehicles", ctypes.c_int),
        ("mGamePhase", ctypes.c_ubyte),
        ("mYellowFlagState", ctypes.c_byte),
        ("mSectorFlag", ctypes.c_ubyte * 3),
        ("mStartLight", ctypes.c_ubyte),
        ("mNumRedLights", ctypes.c_ubyte),
        ("mInRealtime", ctypes.c_bool),
        ("mPlayerName", ctypes.c_char * 32),
        ("mPlrFileName", ctypes.c_char * 64),
        ("mDarkCloud", ctypes.c_double),
        ("mRaining", ctypes.c_double),
        ("mAmbientTemp", ctypes.c_double),
        ("mTrackTemp", ctypes.c_double),
        ("mWind", Vect3),
        ("mMinPathWetness", ctypes.c_double),
        ("mMaxPathWetness", ctypes.c_double),
        ("mGameMode", ctypes.c_ubyte),
        ("mIsPasswordProtected", ctypes.c_bool),
        ("mServerPort", ctypes.c_ushort),
        ("mServerPublicIP", ctypes.c_uint),
        ("mMaxPlayers", ctypes.c_int),
        ("mServerName", ctypes.c_char * 32),
        ("mStartET", ctypes.c_float),
        ("mAvgPathWetness", ctypes.c_double),
        ("mSessionTimeRemaining", ctypes.c_float),
        ("mTimeOfDay", ctypes.c_float),
        ("mIsFixedSetup", ctypes.c_bool),
        ("mTrackGripLevel", ctypes.c_uint8),
        ("mCloudCoverage", ctypes.c_uint8),
        ("mTrackLimitsStepsPerPenalty", ctypes.c_uint8),
        ("mTrackLimitsStepsPerPoint", ctypes.c_uint8),
        ("mExpansion", ctypes.c_ubyte * 187),
        ("mVehiclePointer", ctypes.c_ubyte * 8),
    ]


class ApplicationState(_S):
    _fields_ = [
        ("mAppWindow", ctypes.c_ulonglong),
        ("mWidth", ctypes.c_uint),
        ("mHeight", ctypes.c_uint),
        ("mRefreshRate", ctypes.c_uint),
        ("mWindowed", ctypes.c_uint),
        ("mOptionsLocation", ctypes.c_ubyte),
        ("mOptionsPage", ctypes.c_char * 31),
        ("mExpansion", ctypes.c_ubyte * 204),
    ]


class Events(_S):
    _fields_ = [(n, ctypes.c_uint) for n in (
        "SME_ENTER", "SME_EXIT", "SME_STARTUP", "SME_SHUTDOWN", "SME_LOAD", "SME_UNLOAD",
        "SME_START_SESSION", "SME_END_SESSION", "SME_ENTER_REALTIME", "SME_EXIT_REALTIME",
        "SME_UPDATE_SCORING", "SME_UPDATE_TELEMETRY", "SME_INIT_APPLICATION",
        "SME_UNINIT_APPLICATION", "SME_SET_ENVIRONMENT", "SME_FFB",
    )]


class Generic(_S):
    _fields_ = [
        ("events", Events),
        ("gameVersion", ctypes.c_int),
        ("FFBTorque", ctypes.c_float),
        ("appInfo", ApplicationState),
    ]


class PathData(_S):
    _fields_ = [(n, ctypes.c_char * MAX_PATH) for n in (
        "userData", "customVariables", "stewardResults", "playerProfile", "pluginsFolder",
    )]


class ScoringData(_S):
    _fields_ = [
        ("scoringInfo", ScoringInfo),
        ("scoringStreamSize", ctypes.c_ubyte * 12),
        ("vehScoringInfo", VehicleScoring * MAX_VEHICLES),
        ("scoringStream", ctypes.c_char * 65536),
    ]


class TelemetryHeader(_S):
    _fields_ = [
        ("activeVehicles", ctypes.c_uint8),
        ("playerVehicleIdx", ctypes.c_uint8),
        ("playerHasVehicle", ctypes.c_bool),
    ]


class TelemetryData(_S):
    _fields_ = TelemetryHeader._fields_ + [("telemInfo", VehicleTelemetry * MAX_VEHICLES)]


class ObjectOut(_S):
    _fields_ = [
        ("generic", Generic),
        ("paths", PathData),
        ("scoring", ScoringData),
        ("telemetry", TelemetryData),
    ]


# Décalages utiles (on ne copie que ce dont on a besoin à chaque lecture)
OFF_GENERIC = ObjectOut.generic.offset
OFF_SCORING = ObjectOut.scoring.offset
OFF_SCORING_INFO = OFF_SCORING + ScoringData.scoringInfo.offset
OFF_VEH_SCORING = OFF_SCORING + ScoringData.vehScoringInfo.offset
OFF_TELEMETRY = ObjectOut.telemetry.offset
OFF_TELEM_INFO = OFF_TELEMETRY + TelemetryData.telemInfo.offset
SIZE_TOTAL = ctypes.sizeof(ObjectOut)


def _str(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


class Snapshot:
    """Copie cohérente des données utiles à un instant donné."""

    __slots__ = ("version", "info", "vehicles", "player_scoring", "telem", "has_vehicle", "positions")

    def __init__(self, version, info, vehicles, player_scoring, telem, has_vehicle, positions=None):
        self.positions = positions or {}  # mID -> (x, y, z) monde, pour le spotter
        self.version = version
        self.info = info
        self.vehicles = vehicles
        self.player_scoring = player_scoring
        self.telem = telem
        self.has_vehicle = has_vehicle


class LMUReader:
    """Ouvre la mémoire partagée de LMU et en lit un instantané."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("La mémoire partagée de LMU n'existe que sous Windows.")
        # Sous Windows, ouvrir un nom existant donne accès aux données du jeu ;
        # si le jeu n'est pas lancé, la zone reste à zéro jusqu'à son démarrage.
        self._mm = mmap.mmap(-1, SIZE_TOTAL, SHM_NAME)

    def close(self) -> None:
        self._mm.close()

    def read(self) -> Snapshot | None:
        mm = self._mm
        version = ctypes.c_int.from_buffer_copy(mm, OFF_GENERIC + Generic.gameVersion.offset).value
        info = ScoringInfo.from_buffer_copy(mm, OFF_SCORING_INFO)
        header = TelemetryHeader.from_buffer_copy(mm, OFF_TELEMETRY)
        num = max(0, min(info.mNumVehicles, MAX_VEHICLES))
        vehicles = (VehicleScoring * MAX_VEHICLES).from_buffer_copy(mm, OFF_VEH_SCORING)[:num]
        player_scoring = next((v for v in vehicles if v.mIsPlayer), None)
        if not header.playerHasVehicle or player_scoring is None:
            return Snapshot(version, info, vehicles, player_scoring, None, False)
        n = max(1, min(header.activeVehicles, MAX_VEHICLES))
        allt = (VehicleTelemetry * n).from_buffer_copy(mm, OFF_TELEM_INFO)
        idx = min(header.playerVehicleIdx, n - 1)
        telem = allt[idx]
        if telem.mID != player_scoring.mID:
            # Index décalé : on cherche la voiture du joueur par son identifiant
            telem = next((c for c in allt if c.mID == player_scoring.mID), telem)
        # Positions monde de toutes les voitures (télémétrie, plus fréquente que le classement)
        positions = {c.mID: (c.mPos.x, c.mPos.y, c.mPos.z) for c in allt}
        return Snapshot(version, info, vehicles, player_scoring, telem, True, positions)


__all__ = ["LMUReader", "Snapshot", "SIZE_TOTAL", "_str", "VehicleTelemetry"]
