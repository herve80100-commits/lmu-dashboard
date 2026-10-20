"""Échantillon de télémétrie normalisé, indépendant de la source (jeu ou démo)."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WheelSample:
    temp_c: float = 0.0  # moyenne des 3 zones
    temps_c: tuple = (0.0, 0.0, 0.0)
    pressure_bar: float = 0.0
    wear_pct: float = 0.0  # usure consommée, 0 = neuf
    slip: float = 0.0  # glissement longitudinal (négatif = blocage, positif = patinage)


@dataclass
class Sample:
    # Circuit / session
    track: str = ""
    track_length: float = 0.0  # m
    vehicle: str = ""
    vehicle_class: str = ""
    driver: str = ""
    session_type: str = ""
    time_remaining: Optional[float] = None  # s
    track_temp: float = 0.0
    air_temp: float = 0.0
    raining: float = 0.0

    # Tour
    laps_completed: int = 0
    lap_dist: float = 0.0  # m depuis la ligne
    lap_time: float = 0.0  # temps écoulé dans le tour (s)
    sector: int = 1  # 1, 2 ou 3
    last_lap: float = 0.0
    best_lap: float = 0.0
    last_s1: float = 0.0  # temps du S1 du dernier tour
    last_s2: float = 0.0  # temps cumulé S1+S2 du dernier tour
    session_best_sectors: tuple = (0.0, 0.0, 0.0)  # meilleurs secteurs, toutes voitures
    in_pits: bool = False
    pitstops: int = 0

    # Voiture
    speed: float = 0.0  # m/s
    gear: int = 0
    rpm: float = 0.0
    max_rpm: float = 0.0
    throttle: float = 0.0  # pédale (0-1)
    throttle_filtered: float = 0.0  # après antipatinage
    brake: float = 0.0
    steer: float = 0.0
    brake_bias_front: float = 0.0  # %
    x: float = 0.0
    z: float = 0.0
    fuel: float = 0.0
    fuel_capacity: float = 0.0
    compound: str = ""
    wheels: List[WheelSample] = field(default_factory=lambda: [WheelSample() for _ in range(4)])

    # Course
    position: int = 0
    num_cars: int = 0
    gap_ahead: Optional[float] = None
    ahead_name: str = ""
    gap_behind: Optional[float] = None
    behind_name: str = ""
