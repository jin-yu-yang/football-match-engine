"""Read rcssserver game logs (.rcg, ULG6 text format, optionally gzipped)."""

from __future__ import annotations

import gzip
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_TEAM = re.compile(rb"^\(team \d+ (\S+) (\S+) (\d+) (\d+)")
_PLAYMODE = re.compile(rb"^\(playmode \d+ (\S+)\)")
_FOUL = re.compile(rb"^foul_[a-z_]+_(l|r)$")
_SHOW = re.compile(rb"^\(show (\d+)")


class RcgError(ValueError):
    """The game log has no usable content."""


@dataclass(frozen=True)
class FinalScore:
    left_name: str
    right_name: str
    left: int
    right: int


def open_binary(path: Path):
    path = Path(path)
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def final_score(path: Path) -> FinalScore:
    last = None
    with open_binary(path) as fh:
        for line in fh:
            match = _TEAM.match(line)
            if match:
                last = match
    if last is None:
        raise RcgError(f"{Path(path).name}: no final score (no team line)")
    return FinalScore(last.group(1).decode(), last.group(2).decode(), int(last.group(3)), int(last.group(4)))


def foul_counts(path: Path) -> dict[str, int]:
    counts = {"left": 0, "right": 0}
    with open_binary(path) as fh:
        for line in fh:
            mode = _PLAYMODE.match(line)
            if mode:
                foul = _FOUL.match(mode.group(1))
                if foul:
                    counts["left" if foul.group(1) == b"l" else "right"] += 1
    return counts


def show_cycle(line: bytes) -> int | None:
    match = _SHOW.match(line)
    return int(match.group(1)) if match else None


def game_log(run_dir: Path) -> Path:
    for name in ("match.rcg", "match.rcg.gz"):
        if (run_dir / name).exists():
            return run_dir / name
    raise FileNotFoundError(f"no game log in {run_dir}")


def compress_logs(run_dir: Path) -> None:
    for name in ("match.rcg", "match.rcl"):
        src = run_dir / name
        if src.exists():
            with src.open("rb") as fin, gzip.open(run_dir / f"{name}.gz", "wb") as fout:
                shutil.copyfileobj(fin, fout)
            src.unlink()
