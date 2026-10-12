"""List and apply the repo patch files of a testbed component."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

GROUPS = ("build-fix", "seed")
_NAME = re.compile(r"^(\d{4})-[a-z0-9][a-z0-9-]*\.patch$")


class PatchError(RuntimeError):
    """A patch file is malformed or does not apply."""


@dataclass(frozen=True)
class Patch:
    path: Path
    number: int
    group: str
    reason: str


def _header(path: Path) -> tuple[str, str]:
    group = reason = None
    for line in path.read_text().splitlines():
        if line.startswith("diff --git") or line.startswith("--- "):
            break
        if line.startswith("Group:"):
            group = line.split(":", 1)[1].strip()
        elif line.startswith("Reason:"):
            reason = line.split(":", 1)[1].strip()
    if group not in GROUPS:
        raise PatchError(f"{path.name}: header needs 'Group: build-fix' or 'Group: seed'")
    if not reason:
        raise PatchError(f"{path.name}: header needs a 'Reason:' line")
    return group, reason


def list_patches(component_dir: Path) -> list[Patch]:
    folder = Path(component_dir)
    if not folder.is_dir():
        return []
    patches: dict[int, Patch] = {}
    for path in sorted(folder.glob("*.patch")):
        match = _NAME.match(path.name)
        if not match:
            raise PatchError(f"{path.name}: patch file names must be NNNN-name.patch")
        number = int(match.group(1))
        if number in patches:
            raise PatchError(f"{path.name}: number {number:04d} is used twice")
        group, reason = _header(path)
        patches[number] = Patch(path, number, group, reason)
    return [patches[n] for n in sorted(patches)]


def apply_patches(src_dir: Path, component: str, patches: list[Patch]) -> None:
    for patch in patches:
        check = subprocess.run(["git", "apply", "--check", str(patch.path)], cwd=src_dir,
                               capture_output=True, text=True)
        if check.returncode != 0:
            raise PatchError(f"{component}: patch {patch.path.name} does not apply: {check.stderr.strip()}")
        subprocess.run(["git", "apply", str(patch.path)], cwd=src_dir, check=True,
                       capture_output=True, text=True)


def patch_checksum(patch: Patch) -> str:
    return hashlib.sha256(patch.path.read_bytes()).hexdigest()
