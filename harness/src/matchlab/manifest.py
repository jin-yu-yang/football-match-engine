"""The testbed manifest: what was built, from which pins, and where the binaries are."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import paths

MANIFEST_SCHEMA = 1


class ManifestError(RuntimeError):
    """The manifest is missing or unreadable."""


@dataclass(frozen=True)
class TeamEntry:
    start: Path
    lib_dirs: tuple[Path, ...]


@dataclass(frozen=True)
class Manifest:
    components: dict[str, dict]
    rcssserver: Path
    rcssserver_lib_dirs: tuple[Path, ...]
    rcg2data: Path
    rcg2data_lib_dirs: tuple[Path, ...]
    teams: dict[str, TeamEntry]

    def pins(self) -> dict[str, str]:
        return {name: entry["ref"] for name, entry in sorted(self.components.items())}


def _paths(items) -> list[str]:
    return [str(p) for p in items]


def write_manifest(manifest: Manifest, path: Path) -> None:
    data = {
        "schema": MANIFEST_SCHEMA,
        "components": manifest.components,
        "rcssserver": {"bin": str(manifest.rcssserver), "lib_dirs": _paths(manifest.rcssserver_lib_dirs)},
        "rcg2data": {"bin": str(manifest.rcg2data), "lib_dirs": _paths(manifest.rcg2data_lib_dirs)},
        "teams": {
            name: {"start": str(t.start), "lib_dirs": _paths(t.lib_dirs)}
            for name, t in sorted(manifest.teams.items())
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_manifest(path: Path | None = None) -> Manifest:
    path = Path(path) if path else paths.manifest_path()
    if not path.is_file():
        raise ManifestError(f"testbed manifest not found: {path}. Run `matchlab build` first.")
    try:
        data = json.loads(path.read_text())
        if data.get("schema") != MANIFEST_SCHEMA:
            raise ManifestError(f"{path}: unsupported manifest schema {data.get('schema')}")
        return Manifest(
            components=data["components"],
            rcssserver=Path(data["rcssserver"]["bin"]),
            rcssserver_lib_dirs=tuple(Path(p) for p in data["rcssserver"]["lib_dirs"]),
            rcg2data=Path(data["rcg2data"]["bin"]),
            rcg2data_lib_dirs=tuple(Path(p) for p in data["rcg2data"]["lib_dirs"]),
            teams={
                name: TeamEntry(Path(t["start"]), tuple(Path(p) for p in t["lib_dirs"]))
                for name, t in data["teams"].items()
            },
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{path}: manifest is damaged ({exc}). Run `matchlab build` again.") from exc
