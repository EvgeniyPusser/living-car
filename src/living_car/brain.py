"""Explainable bounded controller. This baseline is explicitly NOT a trained AI."""
from dataclasses import dataclass
import numpy as np
from .body import Body, panel_clearances
from .schema import Experiment

@dataclass
class Decision:
    forces: np.ndarray
    targets: np.ndarray
    explanation: str
    threat: bool

def decide(body: Body, config: Experiment, adaptive: bool, energy_remaining: float, damage: np.ndarray) -> Decision:
    m, d = body.model, body.data
    target = np.zeros(len(body.panel_names))
    forces = np.zeros(m.nu)
    if not adaptive:
        return Decision(forces, target, "Conventional body: passive springs, dampers and crush zones.", False)
    if energy_remaining <= 1:
        return Decision(forces, target, "Energy reserve exhausted: passive mechanical fallback.", False)
    distances = panel_clearances(body)
    frontal = config.scenario in ("frontal", "oblique")
    approach = float(d.qvel[0 if frontal else 1])
    threatened = (distances < config.genome.sensor_range) & (approach > .02)
    if config.scenario == "near_miss":
        # A measured lateral-velocity damper, same on both architectures (in simulation.py).
        threatened &= distances < config.genome.sensor_range
    gain = {"Comfort": .75, "Protection": 1., "Adaptive": .9, "Energy Saving": .45, "Experimental": 1.}[config.mode]
    # Physical protected-cell clearance caps each command regardless of brain mode.
    cap = min(config.genome.max_retraction, .12, .8 * config.genome.yield_displacement)
    if not frontal:
        for i, name in enumerate(body.panel_names):
            if threatened[i] and name.startswith("right"):
                target[i] = cap * gain
        # Neighbor commands share deformation, but high-damage elements are never forced to retract.
        for i, name in enumerate(body.panel_names):
            if damage[i] > .6:
                target[i] = 0
            q, v = d.qpos[body.panel_qpos[i]], d.qvel[body.panel_dofs[i]]
            raw = config.genome.response_gain * (target[i] - q) - 800 * v
            # Limit command energy per step, force and protected-volume travel.
            limit = min(6000., energy_remaining / max(config.dt * (abs(v) + .2), 1e-9))
            forces[body.actuator_ids[i]] = np.clip(raw, -limit, limit)
    else:
        ej = body.engine_joint
        q = d.qpos[m.jnt_qposadr[ej]]
        v = d.qvel[m.jnt_dofadr[ej]]
        engine_target = config.genome.engine_travel * .65 if threatened.any() else 0.
        forces[body.engine_actuator] = np.clip(42000 * (engine_target - q) - 1200 * v, -4000, 4000)
    # Disable any actuator when its remaining-energy allocation would be unsafe.
    velocity = np.abs(d.actuator_velocity)
    worst_step = float(np.sum(np.abs(forces) * (velocity + .2)) * config.dt)
    if worst_step > energy_remaining:
        forces *= energy_remaining / worst_step
    if threatened.any():
        reason = ("Threat detected by body clearance sensors; engine moves on its restrained downward track."
                  if frontal else "Lateral clearance below threshold: retract shell within 120 mm; neighbor tendons share loads.")
    else:
        reason = "No approaching threat: relax shell to its passive shape."
    reason += f" {config.mode} mode. Owner profile remains local."
    return Decision(forces, target, reason, bool(threatened.any()))

def owner_configuration(config: Experiment) -> dict:
    """Local ergonomic targets; no biomechanical injury model is implied."""
    o = config.owner
    return {"seat_rearward_m": round(np.clip((o.height_m - 1.55) * .5, 0, .3), 3),
            "seat_height_m": round(.16 + (1 - o.mobility) * .08, 3),
            "suspension_comfort_target": round(o.comfort, 3),
            "note": "Local ergonomic target; virtual owner, not an anthropometric safety prediction."}
