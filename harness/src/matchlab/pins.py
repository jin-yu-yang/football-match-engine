"""Load and check testbed/pins.toml."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

COMPONENTS: tuple[str, ...] = (
    "rcssserver",
    "librcsc",
    "helios-base",
    "cyrus-lib",
    "cppdnn",
    "eigen",
    "cyrus-team",
    "rcg2data",
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PinError(ValueError):
    """The pins file is missing, incomplete or not exact."""


@dataclass(frozen=True)
class Pin:
    name: str
    kind: str
    url: str
    commit: str | None = None
    tag: str | None = None
    sha256: str | None = None
    strip: str | None = None

    @property
    def ref(self) -> str:
        return self.commit or self.tag or self.sha256 or ""


def load_pins(path: Path) -> dict[str, Pin]:
    try:
        data = tomllib.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise PinError(f"pins file not found: {path}") from exc
    missing = [name for name in COMPONENTS if name not in data]
    if missing:
        raise PinError(f"missing component(s) in {path}: {', '.join(missing)}")
    unknown = sorted(set(data) - set(COMPONENTS))
    if unknown:
        raise PinError(f"unknown component(s) in {path}: {', '.join(unknown)}")
    return {name: _parse(name, data[name]) for name in COMPONENTS}


def _parse(name: str, entry: object) -> Pin:
    if not isinstance(entry, dict):
        raise PinError(f"{name}: entry must be a table")
    if "branch" in entry:
        raise PinError(f"{name}: branch names are not allowed; use a commit or a tag")
    kind = entry.get("kind")
    url = entry.get("url")
    if not url:
        raise PinError(f"{name}: missing url")
    if kind == "git":
        commit, tag = entry.get("commit"), entry.get("tag")
        if bool(commit) == bool(tag):
            raise PinError(f"{name}: set exactly one of commit or tag")
        if commit and not _COMMIT.match(commit):
            raise PinError(f"{name}: commit must be a full 40-character hash")
        return Pin(name, kind, url, commit=commit, tag=tag)
    if kind == "tarball":
        sha = entry.get("sha256")
        if not sha or not _SHA256.match(sha):
            raise PinError(f"{name}: tarball needs a 64-character sha256")
        strip = entry.get("strip")
        if not strip:
            raise PinError(f"{name}: tarball needs strip (its top-level folder)")
        return Pin(name, kind, url, sha256=sha, strip=strip)
    raise PinError(f"{name}: kind must be 'git' or 'tarball'")
