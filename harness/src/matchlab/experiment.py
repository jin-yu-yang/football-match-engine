"""Paired A/B experiments over two arm profiles."""

from __future__ import annotations

import dataclasses
import math
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .manifest import Manifest, load_manifest
from .profile import load_profile
from .repro import replay_and_compare
from .runner import MatchResult, run_matches
from .seeds import MAX_SEED, match_seeds

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_OVERRIDE_SECTIONS = frozenset({"match", "server", "player", "teams"})
_KEYS = frozenset({"name", "matches", "base_seed", "swap_sides", "timeout_s", "arms"})
_ARM_KEYS = frozenset({"profile", "overrides"})


class ExperimentError(ValueError):
    """An experiment file is invalid, or its output folder exists."""


@dataclass(frozen=True)
class Arm:
    name: str
    profile: str
    overrides: dict


@dataclass(frozen=True)
class Experiment:
    name: str
    matches: int
    base_seed: int
    swap_sides: bool
    timeout_s: float
    arms: dict[str, Arm]
    source: Path | None


@dataclass(frozen=True)
class ArmResult:
    profile: str
    profile_hash: str
    matches: list[MatchResult]


@dataclass(frozen=True)
class ExperimentResult:
    name: str
    out_dir: Path
    seeds: list[int]
    arms: dict[str, ArmResult]
    report: dict


def _int(raw: dict, key: str, minimum: int, maximum: int | None = None) -> int:
    value = raw.get(key)
    in_range = isinstance(value, int) and not isinstance(value, bool) and value >= minimum
    if in_range and (maximum is None or value <= maximum):
        return value
    if maximum is None:
        raise ExperimentError(f"{key}: must be a whole number of {minimum} or more")
    raise ExperimentError(f"{key}: must be a whole number from {minimum} to {maximum}")


def load_experiment(path: Path) -> Experiment:
    path = Path(path).resolve()
    try:
        raw = tomllib.loads(path.read_text())
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        raise ExperimentError(f"cannot read experiment {path}: {exc}") from exc
    unknown = sorted(set(raw) - _KEYS)
    if unknown:
        raise ExperimentError(f"unknown key(s): {', '.join(unknown)}")
    name = raw.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        raise ExperimentError("name: use letters, digits, _ or - only")
    swap = raw.get("swap_sides", False)
    if not isinstance(swap, bool):
        raise ExperimentError("swap_sides: must be true or false")
    timeout = raw.get("timeout_s", 3600.0)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ExperimentError("timeout_s: must be a finite number of seconds greater than 0")
    arms_raw = raw.get("arms", {})
    if not isinstance(arms_raw, dict) or set(arms_raw) != {"A", "B"}:
        raise ExperimentError("define exactly two arms A and B ([arms.A] and [arms.B])")
    arms = {}
    for key in ("A", "B"):
        entry = arms_raw[key]
        if not isinstance(entry, dict):
            raise ExperimentError(f"arms.{key}: must be a table")
        unknown_keys = sorted(set(entry) - _ARM_KEYS)
        if unknown_keys:  # a typo such as [arms.B.override.server] must not pass silently
            raise ExperimentError(f"arms.{key}: unknown key(s): {', '.join(unknown_keys)}")
        profile = entry.get("profile")
        if not isinstance(profile, str) or not profile:
            raise ExperimentError(f"arms.{key}.profile: name a profile")
        overrides = entry.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ExperimentError(f"arms.{key}.overrides: must be a table")
        bad = sorted(set(overrides) - _OVERRIDE_SECTIONS)
        if bad:
            raise ExperimentError(f"arms.{key}.overrides: unknown section(s): {', '.join(bad)}")
        arms[key] = Arm(key, profile, overrides)
    return Experiment(name, _int(raw, "matches", 1), _int(raw, "base_seed", 0, MAX_SEED), swap, float(timeout), arms, path)


def _replay_first_match(first: MatchResult, profile, out: Path, manifest: Manifest, timeout_s: float) -> dict:
    result = {"checked_run": "A/0000-normal", "status": "not-checked", "first_difference": None,
              "skipped_prefixes": [], "reason": None}
    if first.status not in ("ok", "extraction-failed"):  # with extraction-failed the game finished and its log exists
        result["reason"] = f"the original match ended with status {first.status}"
        return result
    try:
        repro = replay_and_compare(profile, first.match_seed, first.run_dir, out / "repro-A-0000", manifest,
                                   timeout_s=timeout_s, profile_hash=profile.hash)
    except (RuntimeError, OSError) as exc:  # a missing or unreadable log must not abort the experiment
        result["reason"] = str(exc)
        return result
    result.update(status=repro.status, first_difference=repro.first_difference,
                  skipped_prefixes=list(repro.skipped))
    return result


def run_experiment(experiment: Experiment | str | Path, *, out_dir: Path | None = None, workers: int = 1,
                   manifest: Manifest | None = None) -> ExperimentResult:
    from .report import build_report, write_report

    exp = experiment if isinstance(experiment, Experiment) else load_experiment(Path(experiment))
    manifest = manifest or load_manifest()
    out = Path(out_dir) if out_dir else paths.runs_dir() / exp.name
    if out.exists():
        raise ExperimentError(f"output folder already exists: {out}. Choose another --out or name.")
    base_dir = exp.source.parent if exp.source else None
    profiles = {
        key: load_profile(arm.profile, overrides=arm.overrides, known_teams=manifest.teams.keys(), base_dir=base_dir)
        for key, arm in exp.arms.items()
    }
    seeds = match_seeds(exp.base_seed, exp.matches)
    arms = {}
    for key in ("A", "B"):
        results = run_matches(profiles[key], seeds, out_dir=out / key, manifest=manifest, workers=workers,
                              timeout_s=exp.timeout_s, swap_sides=exp.swap_sides)
        arms[key] = ArmResult(exp.arms[key].profile, profiles[key].hash, results)
    reproducibility = _replay_first_match(arms["A"].matches[0], profiles["A"], out, manifest, exp.timeout_s)
    if reproducibility["status"] != "not-checked":  # run.json of the original now holds the result; mirror it
        first = dataclasses.replace(arms["A"].matches[0], reproducibility=reproducibility["status"])
        arms["A"] = dataclasses.replace(arms["A"], matches=[first, *arms["A"].matches[1:]])
    report = build_report(exp, seeds, arms, reproducibility)
    write_report(out, report)
    return ExperimentResult(exp.name, out, seeds, arms, report)
