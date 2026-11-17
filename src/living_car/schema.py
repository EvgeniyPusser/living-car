"""Versioned, serializable experiment inputs. All physical values use SI units."""
from dataclasses import asdict, dataclass, field, replace
from typing import Literal
import hashlib
import json
import math
import numpy as np

Scenario = Literal["side_contact", "near_miss", "frontal", "oblique", "micro_damage"]
SCENARIOS = {
    "side_contact": ("Lateral contact", "Slow lateral drift into a rigid roadside barrier."),
    "near_miss": ("Narrow clearance", "A finite lateral impulse brings the shell close to a barrier."),
    "frontal": ("Frontal impact", "Low-speed frontal contact; engine travel is measured."),
    "oblique": ("Oblique impact", "Combined longitudinal and lateral initial velocity."),
    "micro_damage": ("Local repair", "Minor coating degradation; finite repair material and energy."),
}

@dataclass(frozen=True)
class Owner:
    name: str = "Alex"
    height_m: float = 1.76
    mobility: float = 0.85
    comfort: float = 0.65
    driving_style: float = 0.45

    def __post_init__(self):
        if not 1.2 <= self.height_m <= 2.2 or not all(0 <= x <= 1 for x in (self.mobility, self.comfort, self.driving_style)):
            raise ValueError("Owner height must be 1.2–2.2 m; preferences must be in [0, 1].")

OWNERS = [Owner(), Owner("Mira", 1.58, 0.45, 0.9, 0.2), Owner("Sam", 1.96, 0.95, 0.4, 0.75)]

@dataclass(frozen=True)
class Genome:
    """Generates panel topology, materials, actuator bounds and control defaults."""
    generation: int = 1
    parent: str | None = None
    panels_per_side: int = 3
    panel_stiffness: float = 90000.0
    panel_damping: float = 1800.0
    coupling_stiffness: float = 22000.0
    yield_displacement: float = 0.035
    max_retraction: float = 0.10
    sensor_range: float = 0.38
    response_gain: float = 42000.0
    repair_rate: float = 0.018
    engine_travel: float = 0.20
    controller_version: str = "bounded-pd-v1"
    schema_version: int = 1

    def __post_init__(self):
        bounds = {
            "panels_per_side": (2, 5), "panel_stiffness": (40000, 150000),
            "panel_damping": (700, 3500), "coupling_stiffness": (5000, 50000),
            "yield_displacement": (0.02, 0.07), "max_retraction": (0.0, 0.12),
            "sensor_range": (0.08, 0.6), "response_gain": (10000, 70000),
            "repair_rate": (0.001, 0.04), "engine_travel": (0.06, 0.22),
        }
        for name, (lo, hi) in bounds.items():
            value = getattr(self, name)
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"Genome {name} outside [{lo}, {hi}].")
        if not isinstance(self.panels_per_side, int) or self.generation < 1:
            raise ValueError("Panel count must be an integer; generation must be positive.")

    @property
    def id(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]

    def mutate(self, seed: int) -> "Genome":
        rng = np.random.default_rng(seed)
        return replace(self, generation=self.generation + 1, parent=self.id,
                       panel_damping=float(np.clip(self.panel_damping * rng.uniform(.8, 1.2), 700, 3500)),
                       coupling_stiffness=float(np.clip(self.coupling_stiffness * rng.uniform(.8, 1.2), 5000, 50000)),
                       max_retraction=float(np.clip(self.max_retraction + rng.uniform(-.025, .015), 0, .12)),
                       sensor_range=float(np.clip(self.sensor_range + rng.uniform(-.07, .07), .08, .6)))

@dataclass(frozen=True)
class Experiment:
    scenario: Scenario = "side_contact"
    seed: int = 42
    speed_mps: float = 1.0
    duration_s: float = 4.0
    dt: float = 0.001
    sample_every: int = 10
    battery_j: float = 12000.0
    repair_material_g: float = 30.0
    mode: str = "Adaptive"
    owner: Owner = field(default_factory=Owner)
    genome: Genome = field(default_factory=Genome)

    def __post_init__(self):
        if self.scenario not in SCENARIOS:
            raise ValueError("Unknown scenario.")
        if not .1 <= self.speed_mps <= 5 or not .5 <= self.duration_s <= 30:
            raise ValueError("Speed must be 0.1–5 m/s; duration 0.5–30 s.")
        if not .0001 <= self.dt <= .002 or not isinstance(self.sample_every, int) or self.sample_every < 1:
            raise ValueError("Use dt 0.0001–0.002 s and a positive sample interval.")
        if self.battery_j < 0 or self.repair_material_g < 0 or not math.isfinite(self.battery_j + self.repair_material_g):
            raise ValueError("Resource budgets must be finite and nonnegative.")
        if self.mode not in ("Comfort", "Protection", "Adaptive", "Energy Saving", "Experimental"):
            raise ValueError("Unknown brain mode.")
