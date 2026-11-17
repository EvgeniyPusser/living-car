from dataclasses import replace
import mujoco
import numpy as np
import pytest
from living_car.body import generate_body
from living_car.brain import decide
from living_car.schema import Experiment, Genome, Owner
from living_car.simulation import compare, mechanical_energy, simulate

def test_passive_free_motion_conserves_energy_and_momentum():
    config = Experiment(scenario="near_miss")
    body = generate_body(config, False)
    energy = mechanical_energy(body)
    velocity = body.data.qvel[:2].copy()
    # No contact, gravity, controller, braking or changing references in this isolated test.
    for _ in range(100):
        mujoco.mj_step(body.model, body.data)
    assert body.data.ncon == 0
    assert mechanical_energy(body) == pytest.approx(energy, rel=1e-9)
    np.testing.assert_allclose(body.data.qvel[:2], velocity, atol=1e-10)

def test_mass_and_initial_conditions_equal_for_paired_architectures():
    config = Experiment()
    a, b = generate_body(config, False), generate_body(config, True)
    assert a.total_mass == b.total_mass
    np.testing.assert_array_equal(a.data.qpos, b.data.qpos)
    np.testing.assert_array_equal(a.data.qvel, b.data.qvel)
    assert mechanical_energy(a) == mechanical_energy(b)

def test_reproducibility_full_trajectory_and_metrics():
    config = Experiment(seed=97, duration_s=1.4)
    a = simulate(config, True)
    b = simulate(config, True)
    assert a.fingerprint == b.fingerprint
    assert a.frames == b.frames

def test_contact_force_is_computed_and_impulse_changes_motion():
    run = simulate(Experiment(duration_s=1.5), False)
    assert run.metrics["peak_contact_force_n"] > 100
    assert run.metrics["contact_impulse_ns"] > 100
    assert run.metrics["mean_residual_damage"] > 0
    assert run.metrics["final_mechanical_energy_j"] < run.metrics["initial_mechanical_energy_j"]
    assert run.metrics["constraint_damping_numerical_balance_j"] >= -run.metrics["initial_mechanical_energy_j"] * .03

def test_timestep_refinement_keeps_impulse_and_damage_close():
    base = Experiment(duration_s=1.5)
    a = simulate(base, False)
    b = simulate(replace(base, dt=.0005, sample_every=20), False)
    assert a.metrics["contact_impulse_ns"] == pytest.approx(b.metrics["contact_impulse_ns"], rel=.05)
    assert a.metrics["mean_residual_damage"] == pytest.approx(b.metrics["mean_residual_damage"], rel=.08)

def test_brain_enforces_force_travel_and_energy_fallback():
    config = Experiment()
    body = generate_body(config, True)
    body.data.qpos[1] = .3
    mujoco.mj_forward(body.model, body.data)
    decision = decide(body, config, True, 1000, np.zeros(len(body.panel_names)))
    assert decision.threat
    assert np.max(np.abs(decision.forces)) <= 6000
    assert decision.targets.max() <= .8 * config.genome.yield_displacement
    assert not decide(body, config, True, 0, np.zeros(len(body.panel_names))).forces.any()

def test_real_neighbor_mechanical_coupling():
    config = Experiment()
    body = generate_body(config, False)
    body.data.qpos[body.panel_qpos[1]] = .02
    mujoco.mj_forward(body.model, body.data)
    # A displaced middle panel generates force at adjacent mechanical DOFs.
    neighbor = body.panel_dofs[0]
    assert abs(body.data.qfrc_passive[neighbor]) > 100

def test_repair_has_finite_energy_and_material_and_does_not_repair_major_damage():
    a = simulate(Experiment(scenario="micro_damage", duration_s=2, battery_j=500, repair_material_g=1), True)
    b = simulate(Experiment(scenario="micro_damage", duration_s=2, battery_j=0, repair_material_g=0), True)
    assert a.metrics["mean_residual_damage"] < b.metrics["mean_residual_damage"]
    assert a.metrics["repair_energy_j"] <= 500 + 1e-7
    assert a.metrics["repair_material_used_g"] <= 1 + 1e-7
    assert b.metrics["repaired_damage_sum"] == 0
    damaged = simulate(Experiment(speed_mps=2, duration_s=2), True)
    assert damaged.metrics["max_permanent_panel_deformation_m"] > .005
    assert damaged.frames[-1]["plastic_m"] == pytest.approx(np.max([f["plastic_m"] for f in damaged.frames], axis=0))

@pytest.mark.parametrize("scenario", ["frontal", "oblique", "near_miss", "micro_damage"])
def test_all_scenarios_finite_and_engine_within_physical_track(scenario):
    run = simulate(Experiment(scenario=scenario, duration_s=1.5), True)
    assert all(np.isfinite(f["qpos"]).all() for f in run.frames)
    # MuJoCo soft joint limits allow a small compliance tolerance, explicitly not hard exact constraints.
    assert run.metrics["max_engine_travel_m"] <= Genome().engine_travel + .01
    assert run.metrics["total_energy_cost_j"] <= 12000 + 5

def test_validation_rejects_invalid_physics_inputs():
    with pytest.raises(ValueError):
        Genome(panel_stiffness=-1)
    with pytest.raises(ValueError):
        Experiment(dt=.1)
    with pytest.raises(ValueError):
        Experiment(speed_mps=float("nan"))
    with pytest.raises(ValueError):
        Owner(height_m=3)
