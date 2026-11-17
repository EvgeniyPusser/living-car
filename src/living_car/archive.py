"""Local SQLite provenance store. Population data never includes owner profiles."""
from dataclasses import asdict
from pathlib import Path
import json
import sqlite3
from .schema import Genome
from .simulation import Run

class Archive:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS genomes(id TEXT PRIMARY KEY, parent TEXT, generation INTEGER, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, genome_id TEXT NOT NULL, architecture TEXT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals(id INTEGER PRIMARY KEY, source_genome TEXT, candidate_genome TEXT, status TEXT, evidence TEXT NOT NULL);
        """)

    def save_genome(self, genome: Genome):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO genomes VALUES(?,?,?,?)", (genome.id, genome.parent, genome.generation, json.dumps(asdict(genome))))

    def save_run(self, run: Run):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?)", (run.fingerprint, run.genome_id, run.architecture, json.dumps(run.to_dict(), allow_nan=False)))

    def save_proposal(self, source: Genome, candidate: Genome, accepted: bool, evidence: dict):
        with self.connection:
            self.connection.execute("INSERT INTO proposals(source_genome,candidate_genome,status,evidence) VALUES(?,?,?,?)", (source.id, candidate.id, "validated" if accepted else "rejected", json.dumps(evidence)))

    def list_genomes(self):
        return [Genome(**json.loads(row[0])) for row in self.connection.execute("SELECT payload FROM genomes ORDER BY generation,id")]

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
