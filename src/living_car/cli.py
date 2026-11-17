"""Desktop launcher and reproducible headless experiments."""
import argparse
from dataclasses import asdict
from pathlib import Path
import json
from .schema import Experiment, Genome, SCENARIOS
from .simulation import compare, paired_summary
from .io import export_pair, load_config, read_pair

def main():
    parser = argparse.ArgumentParser(description="Living Car · Python research simulator")
    sub = parser.add_subparsers(dest="command")
    gui = sub.add_parser("gui", help="Open the interactive Python desktop")
    gui.add_argument("--smoke", action="store_true", help="Render, exercise controls, save screenshot, exit")
    gui.add_argument("--replay", type=Path)
    exp = sub.add_parser("experiment", help="Run an equal-condition paired experiment")
    exp.add_argument("--scenario", choices=list(SCENARIOS), default="side_contact")
    exp.add_argument("--speed", type=float, default=1.)
    exp.add_argument("--seed", type=int, default=42)
    exp.add_argument("--output", type=Path, default=Path("results/first-experiment"))
    exp.add_argument("--config", type=Path)
    evo = sub.add_parser("evolve", help="Mutation search with held-out Pareto validation")
    evo.add_argument("--seed", type=int, default=42)
    evo.add_argument("--candidates", type=int, default=3)
    evo.add_argument("--generations", type=int, default=2)
    evo.add_argument("--output", type=Path, default=Path("results/evolution"))
    collective = sub.add_parser("collective", help="Local virtual Egregor; validate an acquired damping patch")
    collective.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.command in (None, "gui"):
        from .desktop import launch
        launch(smoke=getattr(args, "smoke", False), replay=getattr(args, "replay", None))
    elif args.command == "experiment":
        from .archive import Archive
        from .report import plot_pair, markdown_pair
        config = load_config(json.loads(args.config.read_text(encoding="utf-8"))) if args.config else Experiment(scenario=args.scenario, speed_mps=args.speed, seed=args.seed)
        pair = compare(config)
        args.output.mkdir(parents=True, exist_ok=True)
        export_pair(args.output / "experiment.json", *pair)
        plot_pair(args.output / "comparison.png", *pair)
        (args.output / "RESULTS.md").write_text(markdown_pair(*pair), encoding="utf-8")
        with Archive(args.output / "archive.sqlite") as archive:
            archive.save_genome(config.genome)
            for run in pair:
                archive.save_run(run)
        print(json.dumps(paired_summary(*pair), indent=2))
        print(f"Saved experiment, plots and report to {args.output.resolve()}")
    elif args.command == "evolve":
        from .archive import Archive
        from .evolution import evolve
        if not 1 <= args.generations <= 5:
            parser.error("Use 1–5 generations.")
        args.output.mkdir(parents=True, exist_ok=True)
        genome = Genome()
        reports = []
        with Archive(args.output / "archive.sqlite") as archive:
            for generation in range(args.generations):
                report = evolve(genome, args.seed + generation * 100, args.candidates, archive)
                reports.append(report)
                accepted = [p for p in report["proposals"] if p["accepted"]]
                if not accepted:
                    break
                genome = Genome(**accepted[0]["genome"])
        (args.output / "evolution.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(f"Tested {sum(len(r['proposals']) for r in reports)} proposals. Last accepted generation: {genome.generation}.")
    elif args.command == "collective":
        from .archive import Archive
        from .evolution import collective_improvement
        folder = Path("results/collective")
        folder.mkdir(parents=True, exist_ok=True)
        parent = Genome()
        with Archive(folder / "archive.sqlite") as archive:
            report = collective_improvement([parent, parent.mutate(args.seed), parent.mutate(args.seed+1)], args.seed, archive)
        (folder / "collective.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
