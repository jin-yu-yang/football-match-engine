"""Small statistics helpers (standard library only, deterministic)."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

Z95 = 1.959963984540054
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261011


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def wilson_interval(k: int, n: int, z: float = Z95) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = 0.0 if k == 0 else max(0.0, centre - half)    # exact bounds: no 5e-17 or 0.9999999999999999
    high = 1.0 if k == n else min(1.0, centre + half)
    return [low, high]


def bootstrap_mean_ci(values: Sequence[float], *, resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = BOOTSTRAP_SEED, level: float = 0.95) -> list[float] | None:
    n = len(values)
    if n == 0:
        return None
    # random.Random(seed).random() gives the same sequence on every Python version.
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(n):
            total += values[int(rng.random() * n)]
        means.append(total / n)
    means.sort()
    alpha = 1 - level
    low = means[int(math.floor(alpha / 2 * resamples))]
    high = means[int(math.ceil((1 - alpha / 2) * resamples)) - 1]
    return [low, high]
