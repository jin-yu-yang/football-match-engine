"""SPADL events from rcg2data, and per-match metrics."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from .manifest import Manifest
from .rcg import FinalScore, RcgError, compress_logs, final_score, foul_counts
from .record import update_record

EVENTS_COLUMNS = ["Type", "Side1", "Unum1", "Time1", "Mode1", "X1", "Y1",
                  "Side2", "Unum2", "Time2", "X2", "Y2", "Success"]
METRICS_SCHEMA = 1
SIDES = ("left", "right")
POSSESSION_TYPES = frozenset({"Pass", "Dribble", "Shoot"})


def read_events(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != EVENTS_COLUMNS:
            raise ValueError(f"{Path(path).name}: unexpected events CSV header {reader.fieldnames}")
        return list(reader)


def compute_metrics(score: FinalScore, fouls: dict[str, int], events: list[dict[str, str]]) -> dict:
    count = {name: Counter() for name in ("shots", "passes", "passes_ok", "interceptions", "tackles", "possession")}
    for event in events:
        kind, side1, side2 = event["Type"], event["Side1"], event["Side2"]
        if kind == "Pass" and side1 in SIDES:
            count["passes"][side1] += 1
            if event["Success"] == "true":
                count["passes_ok"][side1] += 1
        elif kind == "Shoot" and side1 in SIDES:
            count["shots"][side1] += 1
        elif kind == "Tackle" and side1 in SIDES:
            count["tackles"][side1] += 1
        elif kind == "Interception" and side2 in SIDES:
            count["interceptions"][side2] += 1
        if kind in POSSESSION_TYPES and side1 in SIDES:
            count["possession"][side1] += 1
    goals = {"left": score.left, "right": score.right}
    names = {"left": score.left_name, "right": score.right_name}
    total_possession = sum(count["possession"].values())
    sides = {}
    for side in SIDES:
        other = "right" if side == "left" else "left"
        passes = count["passes"][side]
        sides[side] = {
            "team": names[side],
            "goals": goals[side],
            "goal_difference": goals[side] - goals[other],
            "shots": count["shots"][side],
            "passes": passes,
            "pass_completion": count["passes_ok"][side] / passes if passes else None,
            "interceptions": count["interceptions"][side],
            "tackles": count["tackles"][side],
            "fouls": fouls.get(side, 0),
            "event_possession_share": (count["possession"][side] / total_possession
                                       if total_possession else None),
        }
    return {"schema": METRICS_SCHEMA, "sides": sides}


def _env(manifest: Manifest) -> dict[str, str]:
    env = os.environ.copy()
    dirs = [str(p) for p in manifest.rcg2data_lib_dirs]
    if dirs:
        env["LD_LIBRARY_PATH"] = ":".join(dirs + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    return env


def extract_and_measure(run_dir: Path, manifest: Manifest) -> dict | None:
    rcg = run_dir / "match.rcg"
    try:
        result = subprocess.run([str(manifest.rcg2data), str(rcg)], cwd=run_dir, env=_env(manifest),
                                capture_output=True, text=True, timeout=600)
        produced = run_dir / "match.event.csv"
        if result.returncode != 0 or not produced.is_file():
            raise RuntimeError(f"rcg2data exit code {result.returncode}: {result.stderr.strip()[-500:]}")
        events_path = run_dir / "events.csv"
        produced.replace(events_path)
        metrics = compute_metrics(final_score(rcg), foul_counts(rcg), read_events(events_path))
    except (RuntimeError, RcgError, ValueError, subprocess.TimeoutExpired) as exc:
        update_record(run_dir, status="extraction-failed", extraction="failed", error=str(exc))
        compress_logs(run_dir)
        return None
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    update_record(run_dir, extraction="ok")
    compress_logs(run_dir)
    return metrics
