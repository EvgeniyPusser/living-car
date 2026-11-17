"""Small genuine genotype search, with held-out validation and explicit trade-offs.

Not neural learning. A conservative Pareto gate can reject every proposal.
"""
from dataclasses import asdict, replace
from .schema import Experiment, Genome
from .simulation import simulate
from .archive import Archive

OBJECTIVES = ("peak_contact_force_n", "mean_residual_damage", "peak_passenger_acceleration_g", "total_energy_cost_j", "max_protected_intrusion_m")

def dominates(candidate: dict, reference: dict, tolerance: float = 1e-7) -> bool:
    return (all(candidate[k] <= reference[k] + tolerance for k in OBJECTIVES)
            and any(candidate[k] < reference[k] - tolerance for k in OBJECTIVES))

def benchmark(genome: Genome, seed: int, speed: float) -> dict:
    runs = [simulate(Experiment(genome=genome, seed=seed, speed_mps=speed, scenario=scenario, duration_s=3.), True)
            for scenario in ("side_contact", "frontal", "near_miss")]
    # Report the worst value of each separate criterion across the validation suite.
    return {key: max(run.metrics[key] for run in runs) for key in OBJECTIVES}

def evolve(genome: Genome, seed: int, candidates: int = 3, archive: Archive | None = None, progress=None) -> dict:
    if not 1 <= candidates <= 12:
        raise ValueError("Use 1–12 candidates per generation.")
    training_reference = benchmark(genome, seed, 1.0)
    validation_reference = benchmark(genome, seed + 10000, 1.35)
    proposals = []
    if archive:
        archive.save_genome(genome)
    for i in range(candidates):
        child = genome.mutate(seed + i)
        train = benchmark(child, seed, 1.0)
        validation = benchmark(child, seed + 10000, 1.35)
        accepted = dominates(train, training_reference) and dominates(validation, validation_reference)
        evidence = {"genome": asdict(child), "id": child.id, "training": train, "validation": validation,
                    "accepted": accepted, "reason": "Pareto improvement in both suites" if accepted else "At least one metric regressed or no strict improvement"}
        proposals.append(evidence)
        if archive:
            archive.save_genome(child)
            archive.save_proposal(genome, child, accepted, evidence)
        if progress:
            progress((i + 1) / candidates)
    return {"parent": asdict(genome), "parent_id": genome.id,
            "training_reference": training_reference, "validation_reference": validation_reference,
            "proposals": proposals,
            "note": "No scalar fitness; non-dominated trade-offs remain visible. Accepted designs require further independent validation."}

def collective_improvement(genomes: list[Genome], seed: int, archive: Archive | None = None) -> dict:
    """Analyze damage across individuals, propose acquired damping, then re-test each body.

    The tested patch is controller/material damping only; incompatible topology is rejected.
    No personal owner data enters this function or its result.
    """
    if not genomes:
        raise ValueError("Population cannot be empty.")
    observations = []
    for i, genome in enumerate(genomes):
        result = simulate(Experiment(genome=genome, seed=seed + i, speed_mps=1.1, duration_s=3), True)
        observations.append({"genome_id": genome.id, "damage": result.metrics["mean_residual_damage"],
                             "acceleration_g": result.metrics["peak_passenger_acceleration_g"],
                             "damping": genome.panel_damping})
    # Acquired experience: select donor from measured damage, retaining the other criteria for validation.
    donor = min(observations, key=lambda row: row["damage"])
    donor_genome = next(g for g in genomes if g.id == donor["genome_id"])
    patches = []
    for genome in genomes:
        compatible = genome.controller_version == donor_genome.controller_version and genome.panels_per_side == donor_genome.panels_per_side
        if not compatible:
            patches.append({"recipient": genome.id, "accepted": False, "reason": "Incompatible topology or controller schema"})
            continue
        child = replace(genome, generation=genome.generation + 1, parent=genome.id, panel_damping=donor["damping"])
        before, after = benchmark(genome, seed + 20000, 1.25), benchmark(child, seed + 20000, 1.25)
        accepted = dominates(after, before)
        evidence = {"recipient": genome.id, "candidate": child.id, "accepted": accepted, "before": before, "after": after,
                    "reason": "Validated transferable damping" if accepted else "No safe Pareto improvement; patch withheld"}
        patches.append(evidence)
        if archive:
            archive.save_genome(genome)
            archive.save_genome(child)
            archive.save_proposal(genome, child, accepted, evidence)
    return {"observations": observations, "donor": donor, "patches": patches,
            "scope": "Local virtual collective; no cloud service or automatic real-vehicle updates."}
