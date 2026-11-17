"""MuJoCo rigid-body contacts + explicit elastoplastic and local-repair approximations."""
from dataclasses import asdict, dataclass
from typing import Callable
import hashlib
import json
import mujoco
import numpy as np
from .body import Body, generate_body, panel_clearances
from .brain import decide, owner_configuration
from .schema import Experiment

MODEL_VERSION = "lc-multibody-0.1"
LIMITATIONS = [
    "Planar rigid multibody model; shell deformation is represented by spring-linked panels, not FEM.",
    "Contact forces are MuJoCo soft-constraint outputs and depend on timestep/contact parameters.",
    "Plasticity is a reduced return-mapping law on mechanical links; no calibrated automotive material data.",
    "Protected-cell damage is a clearance/acceleration proxy, not an injury prediction or crash-test rating.",
    "Adaptive shell and repair mechanisms are hypothetical; this model cannot establish real-world safety.",
    "No tire-road dynamics, airbag, occupant biomechanics, thermal solver or trained neural controller.",
    "Constraint and numerical losses are reported together; the energy residual is not measured heat.",
]

@dataclass
class Run:
    architecture: str
    config: dict
    model_version: str
    genome_id: str
    total_mass_kg: float
    frames: list[dict]
    metrics: dict
    decisions: list[dict]
    limitations: list[str]

    def to_dict(self, include_private: bool = False):
        result = asdict(self)
        if not include_private:
            result["config"].pop("owner", None)
            result["metrics"].pop("ergonomic_configuration", None)
        return result

    @property
    def fingerprint(self):
        # Wall-clock time and owner names never enter reproducibility identity.
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, allow_nan=False).encode()).hexdigest()

def mechanical_energy(body: Body) -> float:
    mujoco.mj_energyPos(body.model, body.data)
    mujoco.mj_energyVel(body.model, body.data)
    return float(body.data.energy.sum())

def simulate(config: Experiment, adaptive: bool, progress: Callable[[float], None] | None = None) -> Run:
    body = generate_body(config, adaptive)
    m, d = body.model, body.data
    n = len(body.panel_names)
    rng = np.random.default_rng(config.seed)
    # Seeded small coating defects; identically initialized in the paired experiment.
    damage = rng.uniform(.08, .12, n) if config.scenario == "micro_damage" else np.zeros(n)
    initial_damage = damage.copy()
    plastic = np.zeros(n)
    crush_names = ("front_crush", "rear_crush")
    crush_plastic = {name: 0. for name in crush_names}
    actuator_work = 0.
    positive_work = 0.
    repair_energy = 0.
    plastic_loss = 0.
    used_material = 0.
    repair_total = 0.
    initial_energy = mechanical_energy(body)
    peak_force, peak_g, peak_intrusion, max_engine_travel = 0., 0., 0., 0.
    max_panel = np.zeros(n)
    frames, decisions = [], []
    previous_reason = ""
    peak_kinetic = float(d.energy[1])
    steps = int(round(config.duration_s / config.dt))
    force_vector = np.zeros(6)
    panel_forces = np.zeros(n)
    max_damage = float(damage.max())
    engine_q = int(m.jnt_qposadr[body.engine_joint])
    stiffness = m.jnt_stiffness[body.panel_joints].copy()
    min_clearance = float("inf")
    contact_impulse = 0.

    def sample(force, acceleration, energy, reason):
        # Store actual simulated transforms, not separately scripted deformation animations.
        mujoco.mj_forward(m, d)
        frames.append({"time_s": round(float(d.time), 8), "qpos": d.qpos.tolist(),
                       "force_n": float(force), "acceleration_g": float(acceleration),
                       "mechanical_j": float(energy), "kinetic_j": float(d.energy[1]),
                       "actuation_j": positive_work, "repair_j": repair_energy,
                       "plastic_loss_j": plastic_loss, "damage": damage.tolist(),
                       "plastic_m": plastic.tolist(), "panel_force_n": panel_forces.tolist(),
                       "stiffness_npm": m.jnt_stiffness[body.panel_joints].tolist(),
                       "panel_displacement_m": d.qpos[body.panel_qpos].tolist(),
                       "clearance_m": float(panel_clearances(body).min()),
                       "engine_travel_m": float(d.qpos[engine_q]),
                       "repair_material_used_g": used_material,
                       "reason": reason})

    sample(0., 0., initial_energy, "Ready: identical mass and initial conditions.")
    for step in range(steps):
        remaining = max(0., config.battery_j - positive_work - repair_energy)
        decision = decide(body, config, adaptive, remaining, damage)
        if decision.explanation != previous_reason:
            decisions.append({"time_s": round(float(d.time), 4), "reason": decision.explanation})
            previous_reason = decision.explanation
        d.ctrl[:] = decision.forces
        d.qfrc_applied[:] = 0
        if config.scenario == "near_miss":
            # Same viscous lateral braking on both models. No hidden adaptive braking advantage.
            d.qfrc_applied[1] = -body.total_mass * .65 * d.qvel[1]
        old_vel = d.qvel.copy()
        old_actuator_vel = d.actuator_velocity.copy()
        mujoco.mj_step(m, d)
        # Midpoint actuator work with no regenerative-credit assumption for battery accounting.
        power = float(np.dot(d.actuator_force, .5 * (old_actuator_vel + d.actuator_velocity)))
        actuator_work += power * config.dt
        positive_work += max(0., power * config.dt)
        force = 0.
        panel_forces[:] = 0
        for ci in range(d.ncon):
            contact = d.contact[ci]
            if body.barrier not in (contact.geom1, contact.geom2):
                continue
            mujoco.mj_contactForce(m, d, ci, force_vector)
            value = float(np.linalg.norm(force_vector[:3]))
            force += value
            other = contact.geom2 if contact.geom1 == body.barrier else contact.geom1
            if other in body.panel_geoms:
                panel_forces[body.panel_geoms.index(other)] += value
        contact_impulse += force * config.dt
        acceleration = float(np.linalg.norm((d.qvel[:2] - old_vel[:2]) / config.dt) / 9.80665)
        peak_force, peak_g = max(peak_force, force), max(peak_g, acceleration)
        min_clearance = min(min_clearance, float(panel_clearances(body).min()))

        # Plastic return map: permanent spring-reference offset after local elastic yield.
        for i, joint in enumerate(body.panel_joints):
            qaddr = body.panel_qpos[i]
            q = float(d.qpos[qaddr])
            max_panel[i] = max(max_panel[i], q)
            elastic = q - plastic[i]
            excess = max(0., elastic - config.genome.yield_displacement)
            if excess:
                old_u = .5 * stiffness[i] * elastic ** 2
                plastic[i] += excess
                new_u = .5 * stiffness[i] * (q - plastic[i]) ** 2
                plastic_loss += max(0., old_u - new_u)
                dref = m.qpos_spring[qaddr]
                m.qpos_spring[qaddr] = plastic[i]
                assert m.qpos_spring[qaddr] >= dref
                damage[i] = max(damage[i], min(1., plastic[i] / .16))
        for name in crush_names:
            joint = m.joint(name).id
            qa = int(m.jnt_qposadr[joint])
            q = float(d.qpos[qa])
            elastic = q - crush_plastic[name]
            excess = max(0., elastic - .055)
            if excess:
                k = float(m.jnt_stiffness[joint])
                plastic_loss += .5 * k * (elastic ** 2 - .055 ** 2)
                crush_plastic[name] += excess
                m.qpos_spring[qa] = crush_plastic[name]
        # Coating-only repair; major plastic distortion is never magically erased.
        if adaptive and d.time > 1 and force < 1:
            eligible = (damage > 0) & (damage <= .2) & (plastic < .005)
            budget_j = max(0., config.battery_j - positive_work - repair_energy)
            budget_g = max(0., config.repair_material_g - used_material)
            increments = np.minimum(damage, config.genome.repair_rate * config.dt) * eligible
            total = float(increments.sum())
            if total:
                scale = min(1., budget_j / (total * 16000), budget_g / (total * 80))
                repair = increments * scale
                repair_total += float(repair.sum())
                damage -= repair
                repair_energy += float(repair.sum()) * 16000
                used_material += float(repair.sum()) * 80
        max_damage = max(max_damage, float(damage.max()))
        # Protected-volume encroachment of shell and engine. Geometry, not a fabricated injury score.
        intrusion = max(0., float(np.max(d.qpos[body.panel_qpos])) - .205)
        engine_displacement = max(0., float(d.qpos[engine_q]))
        engine_rear = 1.32 - .6 * engine_displacement - .30
        engine_top = -.8 * engine_displacement + .23
        if engine_top > -.15:
            intrusion = max(intrusion, -.25 + .98 - engine_rear)
        peak_intrusion = max(peak_intrusion, intrusion)
        max_engine_travel = max(max_engine_travel, engine_displacement)
        energy = mechanical_energy(body)
        peak_kinetic = max(peak_kinetic, float(d.energy[1]))
        if not np.isfinite(d.qpos).all() or np.linalg.norm(d.qvel) > 1e4:
            raise RuntimeError("Simulation diverged; reduce timestep or impact speed.")
        if (step + 1) % config.sample_every == 0 or step == steps - 1:
            sample(force, acceleration, energy, decision.explanation)
        if progress and step % 250 == 0:
            progress(step / steps)
    final_energy = mechanical_energy(body)
    metrics = {
        "peak_contact_force_n": peak_force, "contact_impulse_ns": contact_impulse,
        "peak_passenger_acceleration_g": peak_g, "max_protected_intrusion_m": peak_intrusion,
        "mean_residual_damage": float(damage.mean()), "max_damage": max_damage,
        "max_permanent_panel_deformation_m": float(plastic.max()),
        "front_crush_permanent_m": crush_plastic["front_crush"],
        "max_engine_travel_m": max_engine_travel, "min_panel_clearance_m": min_clearance,
        "initial_mechanical_energy_j": initial_energy, "final_mechanical_energy_j": final_energy,
        "peak_kinetic_energy_j": peak_kinetic, "net_actuator_work_j": actuator_work,
        "actuation_energy_j": positive_work, "repair_energy_j": repair_energy,
        "total_energy_cost_j": positive_work + repair_energy,
        "plastic_dissipation_j": plastic_loss,
        "constraint_damping_numerical_balance_j": initial_energy + actuator_work - final_energy - plastic_loss,
        "repair_material_used_g": used_material, "repaired_damage_sum": repair_total,
        "initial_mean_damage": float(initial_damage.mean()),
        "mass_kg": body.total_mass, "protected_cell_intact": peak_intrusion < .001,
        "ergonomic_configuration": owner_configuration(config),
    }
    return Run("Living Car" if adaptive else "Conventional", asdict(config), MODEL_VERSION,
               config.genome.id, body.total_mass, frames, metrics, decisions, LIMITATIONS)

def compare(config: Experiment) -> tuple[Run, Run]:
    return simulate(config, False), simulate(config, True)

def paired_summary(conventional: Run, living: Run) -> dict:
    fields = ["peak_contact_force_n", "peak_passenger_acceleration_g", "mean_residual_damage",
              "max_protected_intrusion_m", "total_energy_cost_j", "max_permanent_panel_deformation_m"]
    return {key: {"conventional": conventional.metrics[key], "living_car": living.metrics[key],
                  "difference": living.metrics[key] - conventional.metrics[key]} for key in fields}
