"""Deterministic seed derivation (stable across platforms and Python versions)."""

from __future__ import annotations

import hashlib

MAX_SEED = 0x7FFFFFFF  # seeds are 31-bit values


def derive_seed(*parts: object) -> int:
    digest = hashlib.sha256("/".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big") & MAX_SEED


def match_seeds(base_seed: int, n: int) -> list[int]:
    return [derive_seed("match", base_seed, index) for index in range(n)]


def team_seed(match_seed: int, side: str) -> int:
    return derive_seed("team", match_seed, side)
