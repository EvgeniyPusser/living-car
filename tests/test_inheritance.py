from dataclasses import replace
import json
import pytest
from living_car.schema import Experiment, Genome, Owner
from living_car.body import generate_body
from living_car.simulation import compare
from living_car.evolution import dominates, OBJECTIVES
from living_car.archive import Archive
from living_car.io import export_pair, read_pair

def test_genotype_really_generates_different_topology_at_equal_mass():
    a = generate_body(Experiment(genome=Genome(panels_per_side=2)), True)
    b = generate_body(Experiment(genome=Genome(panels_per_side=5)), True)
    assert a.model.nq != b.model.nq
    assert len(a.panel_names) == 4
    assert len(b.panel_names) == 10
    assert a.total_mass == pytest.approx(b.total_mass)

def test_mutation_is_reproducible_bounded_and_has_parentage():
    g = Genome()
    child = g.mutate(42)
    assert child == g.mutate(42)
    assert child != g.mutate(43)
    assert child.parent == g.id
    assert child.generation == 2
    grandchild = child.mutate(7)
    assert grandchild.parent == child.id
    assert grandchild.generation == 3
    for seed in range(100):
        g = g.mutate(seed)

def test_pareto_gate_rejects_tradeoff_and_no_change():
    reference = {k: 10. for k in OBJECTIVES}
    good = dict(reference, mean_residual_damage=9)
    tradeoff = dict(good, total_energy_cost_j=11)
    assert dominates(good, reference)
    assert not dominates(reference, reference)
    assert not dominates(tradeoff, reference)

def test_export_archive_and_replay_exclude_owner_data(tmp_path):
    pair = compare(Experiment(scenario="micro_damage", duration_s=.5, owner=Owner("PRIVATE-OWNER-NAME")))
    path = tmp_path / "pair.json"
    export_pair(path, *pair)
    raw = path.read_text(encoding="utf-8")
    assert "PRIVATE-OWNER-NAME" not in raw
    assert "height_m" not in raw
    assert "ergonomic_configuration" not in raw
    replay = read_pair(path)
    assert replay[0].frames == pair[0].frames
    assert replay[1].metrics["mass_kg"] == pair[1].metrics["mass_kg"]
    with Archive(tmp_path / "archive.sqlite") as archive:
        archive.save_genome(Genome())
        archive.save_genome(Genome().mutate(7))
        archive.save_run(pair[1])
        assert len(archive.list_genomes()) == 2
        saved = archive.connection.execute("SELECT payload FROM runs").fetchone()[0]
        assert "PRIVATE-OWNER-NAME" not in saved

def test_replay_rejects_mismatched_state_dimensions(tmp_path):
    pair = compare(Experiment(duration_s=.5))
    path = tmp_path / "pair.json"
    export_pair(path, *pair)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["runs"][0]["frames"][0]["qpos"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="dimensions"):
        read_pair(path)

@pytest.mark.parametrize("field,value,error", [("time_s", -1, "timestamps"), ("qpos", float("nan"), "coordinates")])
def test_replay_rejects_nonphysical_data(tmp_path, field, value, error):
    pair = compare(Experiment(duration_s=.5))
    path = tmp_path / "pair.json"
    export_pair(path, *pair)
    data = json.loads(path.read_text(encoding="utf-8"))
    frame = data["runs"][0]["frames"][1]
    if field == "qpos":
        frame["qpos"][0] = value
    else:
        frame[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        read_pair(path)
