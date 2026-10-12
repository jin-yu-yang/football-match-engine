"""Repository paths used by the harness."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Return the repository root (the folder that holds testbed/pins.toml)."""
    env = os.environ.get("MATCHLAB_ROOT")
    if env:
        return Path(env).resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "testbed" / "pins.toml").is_file():
            return parent
    raise RuntimeError(f"cannot find the repository root above {__file__}: no testbed/pins.toml")


def testbed_dir() -> Path:
    return repo_root() / "testbed"


def work_dir() -> Path:
    return repo_root() / ".testbed"


def profiles_dir() -> Path:
    return testbed_dir() / "profiles"


def patches_dir() -> Path:
    return testbed_dir() / "patches"


def manifest_path() -> Path:
    return work_dir() / "manifest.json"


def runs_dir() -> Path:
    return repo_root() / "runs"
