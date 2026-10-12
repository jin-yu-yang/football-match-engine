"""Run many matches for one profile with a pool of port slots."""

from __future__ import annotations

import queue
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, load_manifest
from .match import run_single_match
from .metrics import extract_and_measure
from .profile import Profile, ProfileError
from .record import read_record


@dataclass(frozen=True)
class MatchResult:
    index: int
    swapped: bool
    match_seed: int
    run_dir: Path
    status: str
    metrics: dict | None
    reproducibility: str
    missed_cycles: int


def run_matches(profile: Profile, seeds: Sequence[int], *, out_dir: Path, manifest: Manifest | None = None,
                workers: int = 1, timeout_s: float = 3600.0, swap_sides: bool = False,
                cancel: threading.Event | None = None) -> list[MatchResult]:
    if workers < 1:
        raise ValueError("workers must be 1 or more")
    manifest = manifest or load_manifest()
    for side in ("left", "right"):
        team = profile.team(side)["team"]
        if team not in manifest.teams:
            raise ProfileError(f"teams.{side}: unknown team '{team}'; known teams: {', '.join(sorted(manifest.teams))}")
    cancel = cancel or threading.Event()
    jobs = [(i, s, False) for i, s in enumerate(seeds)]
    if swap_sides:
        jobs += [(i, s, True) for i, s in enumerate(seeds)]

    def folder(index: int, swapped: bool) -> Path:
        return out_dir / f"{index:04d}-{'swapped' if swapped else 'normal'}"

    for index, _, swapped in jobs:
        if folder(index, swapped).exists():
            raise FileExistsError(f"run folder already exists: {folder(index, swapped)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    slots: queue.Queue[int] = queue.Queue()
    for slot in range(workers):
        slots.put(slot)

    def job(index: int, seed: int, swapped: bool) -> MatchResult:
        run_dir = folder(index, swapped)
        if cancel.is_set():
            return MatchResult(index, swapped, seed, run_dir, "cancelled", None, "not-checked", 0)
        slot = slots.get()
        try:
            played = profile.swapped() if swapped else profile
            rec = run_single_match(played, match_seed=seed, run_dir=run_dir, manifest=manifest, slot=slot,
                                   timeout_s=timeout_s, profile_hash=profile.hash, swapped=swapped, cancel=cancel)
            metrics = extract_and_measure(run_dir, manifest) if rec.status == "ok" else None
            record = read_record(run_dir)
            return MatchResult(index, swapped, seed, run_dir, record["status"], metrics,
                               record["reproducibility"], record.get("missed_cycles") or 0)
        finally:
            slots.put(slot)

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [pool.submit(job, *j) for j in jobs]
        return [future.result() for future in futures]
    except KeyboardInterrupt:
        cancel.set()  # running matches stop their process groups; queued matches return "cancelled"
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
