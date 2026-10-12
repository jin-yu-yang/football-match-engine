"""Read and write run.json, the record of one match."""

from __future__ import annotations

import json
from pathlib import Path

RUN_SCHEMA = 1


def write_record(run_dir: Path, data: dict) -> None:
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(run_dir / "run.json")


def read_record(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text())


def update_record(run_dir: Path, **fields) -> dict:
    data = read_record(run_dir)
    data.update(fields)
    write_record(run_dir, data)
    return data
