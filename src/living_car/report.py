"""Standalone plots and plain-language paired results from computed trajectories."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from .simulation import Run

def plot_pair(path: str | Path, conventional: Run, living: Run):
    figure = Figure(figsize=(12, 7), facecolor="#101720", layout="constrained")
    axes = figure.subplots(2, 2)
    panels = [("force_n", "Barrier contact force", "kN", 1000),
              ("acceleration_g", "Passenger-cell acceleration", "g", 1),
              ("damage", "Mean residual damage", "fraction", 1),
              ("actuation_j", "Positive actuator work", "J", 1)]
    for ax, (key, title, unit, divisor) in zip(axes.flat, panels):
        ax.set_facecolor("#101720")
        for run, color in ((conventional, "#b3bbc6"), (living, "#59d7c1")):
            ys = [sum(f[key]) / len(f[key]) if key == "damage" else f[key] / divisor for f in run.frames]
            ax.plot([f["time_s"] for f in run.frames], ys, color=color, linewidth=1.8, label=run.architecture)
        ax.set_title(title, color="white", loc="left")
        ax.set_xlabel("Physical time · s", color="#b3bbc6")
        ax.set_ylabel(unit, color="#b3bbc6")
        ax.tick_params(colors="#b3bbc6")
        ax.grid(alpha=.12)
        for spine in ax.spines.values():
            spine.set_color("#36424e")
    axes[0, 0].legend(facecolor="#101720", labelcolor="white", frameon=False)
    figure.suptitle("LIVING CAR / Paired multibody experiment", color="white", fontsize=16)
    figure.text(.01, .002, "Concept: Evgenii Bogomazov-Pusser · Simplified hypothetical model. Not a real crash-test result.", color="#a3aeb9", fontsize=8)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)

def markdown_pair(conventional: Run, living: Run) -> str:
    rows = [("Peak contact force", "peak_contact_force_n", 1000, "kN"),
            ("Peak cabin acceleration", "peak_passenger_acceleration_g", 1, "g"),
            ("Residual damage (model fraction)", "mean_residual_damage", 1, ""),
            ("Permanent panel deformation", "max_permanent_panel_deformation_m", .001, "mm"),
            ("Protected-volume encroachment", "max_protected_intrusion_m", .001, "mm"),
            ("Energy spent on adaptation + repair", "total_energy_cost_j", 1, "J")]
    lines = ["# Living Car — first paired experiment", "", "Concept: Evgenii Bogomazov-Pusser · Living Things / Cloud DNA", "",
             f"Scenario: `{living.config['scenario']}`; speed: {living.config['speed_mps']} m/s; seed: {living.config['seed']}; model: {living.model_version}.",
             f"Equal mass: {living.total_mass_kg:.1f} kg. Genotype: `{living.genome_id}`.", "",
             "| Metric | Conventional | Living Car | Difference (Living − conventional) |", "|---|---:|---:|---:|"]
    for title, key, scale, unit in rows:
        a, b = conventional.metrics[key] / scale, living.metrics[key] / scale
        lines.append(f"| {title} | {a:.4f} {unit} | {b:.4f} {unit} | {b-a:+.4f} {unit} |")
    improved = [title for title, key, _, _ in rows if living.metrics[key] < conventional.metrics[key] - 1e-8]
    worse = [title for title, key, _, _ in rows if living.metrics[key] > conventional.metrics[key] + 1e-8]
    lines += ["", "This is a hypothesis test, not evidence of real automotive safety.", "",
              "Lower in Living Car: " + (", ".join(improved) or "none") + ".",
              "Higher in Living Car: " + (", ".join(worse) or "none") + ".", "",
              "Damage is a link-plasticity/coating proxy. Contact peaks are solver/timestep dependent.",
              "No single aggregate safety score is assigned. Different metrics may favor different architectures.", "",
              "## Model limitations", ""]
    lines += [f"- {line}" for line in living.limitations]
    return "\n".join(lines) + "\n"
