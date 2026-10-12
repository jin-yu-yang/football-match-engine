"""Replay a match and compare the game logs byte for byte."""

from __future__ import annotations

import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .manifest import Manifest
from .match import run_single_match
from .profile import Profile
from .rcg import compress_logs, game_log, open_binary, show_cycle
from .record import update_record

# Line prefixes that hold no match data (decided in Task 8). Each skipped prefix is reported.
SKIP_PREFIXES: tuple[bytes, ...] = (b"(server_param", b"(msg ")


class ReproError(RuntimeError):
    """A run of the reproducibility check did not finish."""


@dataclass(frozen=True)
class ReproResult:
    status: str
    first_difference: dict | None
    skipped: tuple[str, ...]


EXCERPT_BEFORE = 80  # bytes shown before the first differing byte
EXCERPT_AFTER = 120  # bytes shown from the first differing byte on


def _offset(a: bytes | None, b: bytes | None) -> int:
    """Index of the first differing byte, or the length of the shorter line."""
    a, b = a or b"", b or b""
    limit = min(len(a), len(b))
    for i in range(limit):
        if a[i] != b[i]:
            return i
    return limit


def _excerpt(line: bytes | None, offset: int) -> str:
    if line is None:
        return "<end of file>"
    text = line.rstrip(b"\n")
    start = max(0, offset - EXCERPT_BEFORE)
    end = offset + EXCERPT_AFTER
    piece = text[start:end].decode(errors="replace")
    return ("..." if start > 0 else "") + piece + ("..." if end < len(text) else "")


def compare_rcg(a: Path, b: Path, skip_prefixes: tuple[bytes, ...] = SKIP_PREFIXES) -> ReproResult:
    skipped = tuple(p.decode() for p in skip_prefixes)
    cycle = None
    with open_binary(a) as fa, open_binary(b) as fb:
        for number, (la, lb) in enumerate(itertools.zip_longest(fa, fb), start=1):
            if la is not None:
                found = show_cycle(la)
                cycle = found if found is not None else cycle
            if la == lb:
                continue
            if la is not None and lb is not None and any(
                    la.startswith(p) and lb.startswith(p) for p in skip_prefixes):
                continue
            offset = _offset(la, lb)
            difference = {"line": number, "cycle": cycle, "offset": offset,
                          "a": _excerpt(la, offset), "b": _excerpt(lb, offset)}
            return ReproResult("differs", difference, skipped)
    return ReproResult("identical", None, skipped)


def replay_and_compare(profile: Profile, match_seed: int, original_run_dir: Path, replay_dir: Path,
                       manifest: Manifest, *, slot: int = 0, timeout_s: float = 3600.0,
                       profile_hash: str | None = None) -> ReproResult:
    rec = run_single_match(profile, match_seed=match_seed, run_dir=replay_dir, manifest=manifest, slot=slot,
                           timeout_s=timeout_s, profile_hash=profile_hash)
    if rec.status != "ok":
        raise ReproError(f"the replay did not finish ({rec.status}: {rec.error}); see {replay_dir}")
    result = compare_rcg(game_log(original_run_dir), game_log(replay_dir))
    for run_dir in (original_run_dir, replay_dir):
        update_record(run_dir, reproducibility=result.status)
        compress_logs(run_dir)
    return result


def check_reproducibility(profile: Profile, match_seed: int, out_dir: Path, manifest: Manifest, *,
                          slot: int = 0, timeout_s: float = 3600.0) -> ReproResult:
    out_dir.mkdir(parents=True, exist_ok=False)
    first = run_single_match(profile, match_seed=match_seed, run_dir=out_dir / "a", manifest=manifest,
                             slot=slot, timeout_s=timeout_s)
    if first.status != "ok":
        raise ReproError(f"run a did not finish ({first.status}: {first.error}); see {first.run_dir}")
    result = replay_and_compare(profile, match_seed, out_dir / "a", out_dir / "b", manifest,
                                slot=slot, timeout_s=timeout_s)
    (out_dir / "repro.json").write_text(json.dumps(
        {"profile_hash": profile.hash, "match_seed": match_seed, **asdict(result)}, indent=2, sort_keys=True) + "\n")
    return result
