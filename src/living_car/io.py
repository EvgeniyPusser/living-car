"""Explicit schema loading and portable experiment export/replay."""
from pathlib import Path
import json
import math
from .schema import Experiment, Genome, Owner
from .simulation import Run, paired_summary

def load_config(data: dict) -> Experiment:
    data = dict(data)
    data["genome"] = Genome(**data.get("genome", {}))
    data["owner"] = Owner(**data.get("owner", {}))
    return Experiment(**data)

def export_pair(path: str | Path, conventional: Run, living: Run):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "summary": paired_summary(conventional, living),
               "runs": [conventional.to_dict(), living.to_dict()],
               "privacy": "Owner profiles and derived ergonomic settings excluded. Simulation remains local."}
    path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")

def read_pair(path: str | Path) -> tuple[Run, Run]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or len(payload.get("runs", [])) != 2:
        raise ValueError("Expected a version-1 paired Living Car experiment export.")
    runs = tuple(Run(**value) for value in payload["runs"])
    if runs[0].architecture != "Conventional" or runs[1].architecture != "Living Car":
        raise ValueError("Unexpected paired architecture order.")
    for run in runs:
        config = load_config(run.config)
        from .body import generate_body
        nq = generate_body(config, run.architecture == "Living Car").model.nq
        if not run.frames or any(len(f["qpos"]) != nq for f in run.frames):
            raise ValueError("Replay frame dimensions do not match the saved genotype.")
        times = [f["time_s"] for f in run.frames]
        if any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("Replay timestamps must be finite and strictly increasing.")
        if any(not all(math.isfinite(q) for q in f["qpos"]) for f in run.frames):
            raise ValueError("Replay coordinates must be finite.")
    return runs
