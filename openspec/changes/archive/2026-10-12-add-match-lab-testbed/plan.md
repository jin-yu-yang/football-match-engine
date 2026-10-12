# Match-Lab Testbed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. When a task is done, also check off the `tasks.md` items listed in its **Covers** line.

**Goal:** A Python harness (`matchlab`) that builds the RoboCup testbed from pinned sources plus repo patches, runs seeded matches under TOML profiles, extracts SPADL events and metrics, and reports paired A/B experiments with confidence intervals.

**Architecture:** Testbed data (pins, patches, profile presets) lives in `testbed/`. The Python package lives in `harness/src/matchlab/`, with one module per responsibility. The build writes only into `.testbed/` and records a manifest there. The runner reads binaries only from that manifest and writes each match into its own run folder. Experiments call the same `run_matches` API as the CLI.

**Tech Stack:** Python 3.14 (standard library only at run time: `tomllib`, `subprocess`, `concurrent.futures`, `hashlib`, `gzip`, `csv`, `json`, `random`), pytest (development only), Git, autotools and CMake for the C++ components.

**Spec:** `openspec/changes/add-match-lab-testbed/design.md` and `openspec/changes/add-match-lab-testbed/specs/{testbed-build,match-runner,match-metrics,benchmark-experiments}/spec.md`. Read both before each task.

## Global Constraints

- Python requirement in `pyproject.toml`: `requires-python = ">=3.11"`. Runtime dependencies: none. Development dependency: `pytest>=8`. Build backend: `setuptools>=77` (older versions reject the SPDX `license` string).
- Commands that can run longer than 10 minutes (the full testbed build, the spike, the demo experiment) run with the Bash tool's `run_in_background` option and write to a log file. Wait for the completion notice, then read the log.
- Foreground commands that run real matches (the integration tests, the full suite after Task 6) pass the Bash tool's `timeout` parameter as `600000` (10 minutes); the default is 2 minutes.
- Server values that the harness sets for every match (reserved; profiles cannot set them): ports, `synch_mode=true`, `auto_mode=true`, `random_seed`, `connect_wait=100000000`, `kick_off_wait=300`, `synch_wait_clients` = 22 + the number of teams with `coach = true` (the rcssserver hold patch 0003: the server does not step before that many clients are connected), logging on, fixed log names `match.rcg` / `match.rcl`, no server-side log compression, `game_log_version=6` (the ULG6 text format the parsers read), `nr_normal_halfs` and `half_time` (from `[match]`).
- Team start order: start the left team, wait until `server.log` shows its 11 players (and its coach when `coach = true`), then the same for the right team. Connect timeout: 60 s per team. Coaches are on by default.
- Run statuses: `running`, `ok`, `error`, `timeout`, `cancelled`, `extraction-failed`. Every run record has `missed_cycles` (count of "Someone missed a cycle" lines).
- Package license field: `license = "GPL-3.0-or-later"`. Root `LICENSE` = the GPLv3 text, SHA-256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.
- The build writes only under `.testbed/`. Match output goes under `runs/` or a folder the user names. Never change the user's trees in `~/` (`~/librcsc`, `~/rcssserver-19.0.0`, and so on); read from them only.
- Components, in build order: `rcssserver`, `librcsc`, `helios-base`, `cyrus-lib`, `cppdnn`, `eigen`, `cyrus-team`, `rcg2data`.
- Port slots: base port `16000`, stride `10`; slot `k` uses ports `16000+10k` (players), `+1` (coach), `+2` (online coach).
- Seed derivation: SHA-256 of `"/".join(str(p) for p in parts)`, first 4 bytes big-endian, masked with `0x7FFFFFFF`. Match seed = `derive_seed("match", base_seed, index)`. Team seed = `derive_seed("team", match_seed, side)`.
- Client seed transport: environment variable `RCSC_RANDOM_SEED` (decimal).
- Bootstrap: 10,000 resamples, seed `20261011`, percentile method, level 0.95.
- Default parallel workers: 1. Default match timeout: 3600 s.
- Docs and user-facing messages: simplified technical English (short sentences, active voice).
- Every commit message ends with the trailer line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run the tests from the repo root with `harness/.venv/bin/pytest harness/tests -q`.

## Review Focus

1. **Ctrl-C or an exception during a match** must leave no rcssserver or player processes alive, also when matches run in worker threads. Tests: Task 11, `test_interrupt_kills_processes` and `test_cancel_stops_match`; Task 14, `test_cancel_stops_batch`.
2. **A port that is already in use** (for example a manual rcssserver on the same slot) must give a clear error before any process starts. Test: Task 11, `test_port_in_use_starts_nothing`.
3. **Profile values of the wrong shape** (a table, a list, a string with spaces, a reserved key, the same team name on both sides) must be rejected with a message that names the key. Test: Task 9, `test_rejects_bad_values`.
4. **A truncated or broken game log** (timeout, crash, no `team` line) must give status `extraction-failed` or `timeout` and no metrics, and the experiment must exclude that pair. Tests: Task 13, `test_log_without_score_is_extraction_failure`; Task 16, `test_failed_pairs_are_excluded`.
5. **An existing output folder** must not be overwritten (it may hold earlier results). Tests: Task 14, `test_existing_run_folder_is_refused`; Task 16, `test_existing_experiment_folder_is_refused`.

---

### Task 1: Repository scaffold

**Covers:** tasks.md 1.1, 1.2, 1.3, 1.4

**Files:**
- Create: `.gitignore` (modify if present), `LICENSE`, `harness/pyproject.toml`, `harness/src/matchlab/__init__.py`, `harness/src/matchlab/paths.py`, `harness/tests/test_paths.py`, `testbed/pins.toml` (placeholder content in Task 2), `testbed/patches/.gitkeep`, `testbed/profiles/.gitkeep`

**Interfaces:**
- Produces: `matchlab.paths.repo_root() -> Path`, `work_dir() -> Path` (`<root>/.testbed`), `testbed_dir() -> Path`, `profiles_dir() -> Path`, `patches_dir() -> Path`, `manifest_path() -> Path` (`<root>/.testbed/manifest.json`), `runs_dir() -> Path`.

- [ ] **Step 1: Write `.gitignore`**

```gitignore
.superpowers/
.testbed/
runs/
harness/.venv/
__pycache__/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 2: Add the license**

Run: `cp ~/helios-base/COPYING LICENSE && sha256sum LICENSE`
Expected: `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986  LICENSE`

- [ ] **Step 3: Write `harness/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "matchlab"
version = "0.1.0"
description = "Match-lab harness: build the RoboCup testbed, run seeded matches, report A/B experiments."
requires-python = ">=3.11"
license = "GPL-3.0-or-later"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
matchlab = "matchlab.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["testbed: needs a built testbed (.testbed/manifest.json); skipped otherwise"]
```

- [ ] **Step 4: Create the folders and an empty pins file**

Run:
```bash
mkdir -p harness/src/matchlab harness/tests testbed/patches testbed/profiles
touch testbed/patches/.gitkeep testbed/profiles/.gitkeep
printf '# Pinned testbed components. Filled in by Task 2.\n' > testbed/pins.toml
```

- [ ] **Step 5: Write the failing test `harness/tests/test_paths.py`**

```python
from pathlib import Path

from matchlab import paths


def test_repo_root_contains_pins():
    root = paths.repo_root()
    assert (root / "testbed" / "pins.toml").is_file()


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MATCHLAB_ROOT", str(tmp_path))
    assert paths.repo_root() == tmp_path.resolve()
    assert paths.work_dir() == tmp_path.resolve() / ".testbed"
    assert paths.manifest_path() == tmp_path.resolve() / ".testbed" / "manifest.json"
    assert paths.profiles_dir() == tmp_path.resolve() / "testbed" / "profiles"
```

- [ ] **Step 6: Create the virtual environment and run the test to see it fail**

Run:
```bash
python3 -m venv harness/.venv
harness/.venv/bin/pip install -q -e 'harness[dev]'
harness/.venv/bin/pytest harness/tests -q
```
Expected: FAIL (`ImportError: cannot import name 'paths'`).

- [ ] **Step 7: Write `harness/src/matchlab/__init__.py` and `paths.py`**

`__init__.py`:
```python
"""matchlab: build the RoboCup testbed, run seeded matches, report A/B experiments."""

__version__ = "0.1.0"
```

`paths.py`:
```python
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
```

- [ ] **Step 8: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests -q`
Expected: `2 passed`.

- [ ] **Step 9: Commit**

```bash
git add .gitignore LICENSE harness/pyproject.toml harness/src harness/tests testbed
git commit -m "chore(harness): scaffold matchlab package, testbed folders and GPLv3 license" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Pins file and loader

**Covers:** tasks.md 2.1

**Files:**
- Modify: `testbed/pins.toml`
- Create: `harness/src/matchlab/pins.py`, `harness/tests/test_pins.py`

**Interfaces:**
- Produces: `COMPONENTS: tuple[str, ...]` (build order, see Global Constraints); `class PinError(ValueError)`; `@dataclass(frozen=True) class Pin(name: str, kind: str, url: str, commit: str | None = None, tag: str | None = None, sha256: str | None = None, strip: str | None = None)` with property `ref -> str`; `load_pins(path: Path) -> dict[str, Pin]`.

- [ ] **Step 1: Write `testbed/pins.toml`**

```toml
# Pinned testbed components. Each entry names exactly one immutable reference:
# a full commit hash, a release tag, or a release tarball with its SHA-256.
# Branch names are not allowed.

[rcssserver]
kind = "tarball"
url = "https://github.com/rcsoccersim/rcssserver/releases/download/rcssserver-19.0.0/rcssserver-19.0.0.tar.gz"
sha256 = "08abeef0bf94816a9886647fd578da0dc58d40b08bb6a27ed85cddc2acce2aea"
strip = "rcssserver-19.0.0"

[librcsc]
kind = "git"
url = "https://github.com/helios-base/librcsc.git"
commit = "65e139327751f2f45d9b5a03b1f59fb5ca700cd2"

[helios-base]
kind = "git"
url = "https://github.com/helios-base/helios-base.git"
commit = "66fd63d6f9d022423b8c4430668a2b8510353caf"

[cyrus-lib]
kind = "git"
url = "https://github.com/Cyrus2D/cyrus-soccer-simulation-lib.git"
commit = "6bafd9b9241a11c3149d449a2b8d8c04fc13f31e"

[cppdnn]
kind = "git"
url = "https://github.com/Cyrus2D/CppDNN.git"
commit = "8cb5a5551e1a950dc60e445a5f73f965aa939bbc"

[eigen]
kind = "git"
url = "https://gitlab.com/libeigen/eigen.git"
tag = "3.4.0"

[cyrus-team]
kind = "git"
url = "https://github.com/naderzare/cyrus-soccer-simulation-team.git"
commit = "335497b715770af427e1b0fbaba3f4290b406c3f"

[rcg2data]
kind = "git"
url = "https://github.com/hidehisaakiyama/rcg2data.git"
commit = "30970645c204529faa0baa5f15c83f91c5bcc1fb"
```

- [ ] **Step 2: Write the failing tests `harness/tests/test_pins.py`**

```python
import pytest

from matchlab import paths
from matchlab.pins import COMPONENTS, PinError, load_pins

GOOD_GIT = 'kind = "git"\nurl = "https://example.org/x.git"\ncommit = "' + "a" * 40 + '"\n'


def write(tmp_path, body):
    path = tmp_path / "pins.toml"
    path.write_text(body)
    return path


def all_components(entry):
    return "".join(f"[{name}]\n{entry}\n" for name in COMPONENTS)


def test_repo_pins_cover_every_component():
    pins = load_pins(paths.testbed_dir() / "pins.toml")
    assert set(pins) == set(COMPONENTS)
    assert pins["rcssserver"].kind == "tarball"
    assert pins["eigen"].tag == "3.4.0"
    assert pins["librcsc"].ref == "65e139327751f2f45d9b5a03b1f59fb5ca700cd2"


def test_rejects_branch(tmp_path):
    body = all_components(GOOD_GIT).replace(
        '[librcsc]\nkind = "git"', '[librcsc]\nbranch = "master"\nkind = "git"'
    )
    with pytest.raises(PinError, match="librcsc: branch names are not allowed"):
        load_pins(write(tmp_path, body))


def test_rejects_short_commit(tmp_path):
    body = all_components('kind = "git"\nurl = "u"\ncommit = "65e1393"\n')
    with pytest.raises(PinError, match="full 40-character"):
        load_pins(write(tmp_path, body))


def test_rejects_missing_component(tmp_path):
    body = "".join(f"[{name}]\n{GOOD_GIT}\n" for name in COMPONENTS[:-1])
    with pytest.raises(PinError, match="missing component.*rcg2data"):
        load_pins(write(tmp_path, body))


def test_rejects_tarball_without_checksum(tmp_path):
    body = all_components(GOOD_GIT).replace(
        '[rcssserver]\n' + GOOD_GIT, '[rcssserver]\nkind = "tarball"\nurl = "u"\nstrip = "x"\n'
    )
    with pytest.raises(PinError, match="rcssserver: tarball needs a 64-character sha256"):
        load_pins(write(tmp_path, body))


def test_rejects_both_commit_and_tag(tmp_path):
    body = all_components(GOOD_GIT + 'tag = "v1"\n')
    with pytest.raises(PinError, match="exactly one of commit or tag"):
        load_pins(write(tmp_path, body))
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `harness/.venv/bin/pytest harness/tests/test_pins.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'matchlab.pins'`).

- [ ] **Step 4: Write `harness/src/matchlab/pins.py`**

```python
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
```

- [ ] **Step 5: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_pins.py -q`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add testbed/pins.toml harness/src/matchlab/pins.py harness/tests/test_pins.py
git commit -m "feat(testbed): pin the eight testbed components and validate the pins file" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Patch files: listing and ordered application

**Covers:** tasks.md 2.4

**Files:**
- Create: `harness/src/matchlab/patches.py`, `harness/tests/test_patches.py`

**Interfaces:**
- Produces: `GROUPS = ("build-fix", "seed")`; `class PatchError(RuntimeError)`; `@dataclass(frozen=True) class Patch(path: Path, number: int, group: str, reason: str)`; `list_patches(component_dir: Path) -> list[Patch]` (empty list if the folder does not exist; sorted by number); `apply_patches(src_dir: Path, component: str, patches: list[Patch]) -> None`; `patch_checksum(patch: Patch) -> str` (SHA-256 hex of the file bytes).

Patch file format (text before the first `diff --git` line is ignored by `git apply`):
```text
Group: build-fix
Reason: <one line>

diff --git a/... b/...
```
File names: `NNNN-<kebab-words>.patch`, for example `0001-build-fix-missing-includes.patch`.

- [ ] **Step 1: Write the failing tests `harness/tests/test_patches.py`**

```python
import subprocess

import pytest

from matchlab.patches import PatchError, apply_patches, list_patches, patch_checksum


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


def make_repo(path):
    path.mkdir()
    git(path, "init", "-q")
    (path / "a.txt").write_text("one\n")
    git(path, "add", "a.txt")
    git(path, "commit", "-q", "-m", "init")
    return path


def diff_for(repo, new_text):
    (repo / "a.txt").write_text(new_text)
    out = subprocess.run(["git", "diff"], cwd=repo, check=True, capture_output=True, text=True).stdout
    git(repo, "checkout", "--", "a.txt")
    return out


def write_patch(folder, name, group, body):
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(f"Group: {group}\nReason: test\n\n{body}")
    return path


def test_lists_in_numeric_order_and_applies(tmp_path):
    repo = make_repo(tmp_path / "src")
    first = diff_for(repo, "one\ntwo\n")
    (repo / "a.txt").write_text("one\ntwo\n")
    git(repo, "commit", "-q", "-am", "two")
    second = diff_for(repo, "one\ntwo\nthree\n")  # relative to the state after the first patch
    git(repo, "reset", "-q", "--hard", "HEAD~1")
    folder = tmp_path / "patches"
    write_patch(folder, "0002-add-three.patch", "seed", second)
    write_patch(folder, "0001-add-two.patch", "build-fix", first)

    patches = list_patches(folder)
    assert [p.number for p in patches] == [1, 2]
    assert [p.group for p in patches] == ["build-fix", "seed"]

    apply_patches(repo, "demo", patches)
    assert (repo / "a.txt").read_text() == "one\ntwo\nthree\n"
    assert len(patch_checksum(patches[0])) == 64


def test_failure_names_component_and_patch(tmp_path):
    repo = make_repo(tmp_path / "src")
    body = diff_for(repo, "changed\n").replace("-one", "-not-there")
    folder = tmp_path / "patches"
    write_patch(folder, "0001-broken.patch", "build-fix", body)
    with pytest.raises(PatchError, match=r"demo: patch 0001-broken.patch does not apply"):
        apply_patches(repo, "demo", list_patches(folder))


def test_missing_folder_means_no_patches(tmp_path):
    assert list_patches(tmp_path / "none") == []


def test_rejects_bad_name_and_header(tmp_path):
    folder = tmp_path / "patches"
    write_patch(folder, "fix.patch", "build-fix", "")
    with pytest.raises(PatchError, match="NNNN-name.patch"):
        list_patches(folder)
    (folder / "fix.patch").unlink()
    (folder / "0001-x.patch").write_text("Reason: no group\n\ndiff --git a/a b/a\n")
    with pytest.raises(PatchError, match="Group"):
        list_patches(folder)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `harness/.venv/bin/pytest harness/tests/test_patches.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `harness/src/matchlab/patches.py`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_patches.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add harness/src/matchlab/patches.py harness/tests/test_patches.py
git commit -m "feat(testbed): list and apply numbered component patches" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Build-fix and seed patches, and the rcssserver tarball check

**Covers:** tasks.md 2.2, 2.3 (check off now); the patch files of 3.1 and 3.2 (check those off in Task 7, after the checks)

**Files:**
- Create: `testbed/patches/librcsc/0001-build-fix-missing-includes.patch`, `testbed/patches/librcsc/0002-build-fix-simdjson-gcc15.patch`, `testbed/patches/librcsc/0003-seed-env-random-seed.patch`, `testbed/patches/cyrus-lib/0001-build-fix-boost-system-header-only.patch`, `testbed/patches/cyrus-lib/0002-build-fix-missing-include.patch`, `testbed/patches/cyrus-lib/0003-seed-env-random-seed.patch`, `testbed/patches/cyrus-team/0001-build-fix-cmake-dependencies.patch`, `testbed/patches/cyrus-team/0002-build-fix-rapidjson-gcc15.patch`, `testbed/patches/rcssserver/NNNN-seed-random-seed-param.patch`; maybe `testbed/patches/rcssserver/0001-build-fix-*.patch` (only if Step 2 finds source differences)
- Modify: `openspec/changes/add-match-lab-testbed/design.md` (Open Questions rows about the tarball and Cyrus seeding)

**Interfaces:**
- Consumes: the patch file format from Task 3.
- Produces: all patch files that the single build in Task 6 applies. The seed patches are written here, against the check trees, so the testbed is built only once.

The user's local trees (`~/librcsc`, `~/cyrus-soccer-simulation-lib`, `~/cyrus-soccer-simulation-team`) hold these fixes as uncommitted diffs. Read them; do not change them.

- [ ] **Step 1: Download the rcssserver release and check its SHA-256**

Run:
```bash
mkdir -p .testbed/check && cd .testbed/check
curl -sSLo rcssserver-19.0.0.tar.gz https://github.com/rcsoccersim/rcssserver/releases/download/rcssserver-19.0.0/rcssserver-19.0.0.tar.gz
sha256sum rcssserver-19.0.0.tar.gz
tar xzf rcssserver-19.0.0.tar.gz
cd ../..
```
Expected: `08abeef0bf94816a9886647fd578da0dc58d40b08bb6a27ed85cddc2acce2aea  rcssserver-19.0.0.tar.gz`. If it differs, stop and report to the controller.

- [ ] **Step 2: Compare the release sources with the local build tree**

Run:
```bash
diff -rq .testbed/check/rcssserver-19.0.0/src ~/rcssserver-19.0.0/src \
  | grep -vE '\.(o|a|lo|la|rc[gl])\b|/\.deps|/\.libs|Makefile$|: rcssserver$|: rcsoccersim$|Only in /home/[^/]+/rcssserver-19.0.0/src: (rcssserver|rcsoccersim|.*\.o)$' || true
```
Expected: no lines, or only generated files that the build makes (for example parser outputs `*.tab.*`, `*.cc` from flex/bison). For each remaining file that is a **source** difference, create `testbed/patches/rcssserver/0001-build-fix-<topic>.patch` with `diff -u` output rewritten to `a/src/<file>` / `b/src/<file>` paths and a `Group: build-fix` header. Record the result ("no source differences" or the list of patches) in `design.md` Open Questions, row "Does the local rcssserver tarball differ…", column "Owner" → "Resolved in Task 4: <result>".

- [ ] **Step 3: Write the librcsc build-fix patches**

Run:
```bash
mkdir -p testbed/patches/librcsc
{ printf 'Group: build-fix\nReason: GCC 15 needs explicit <algorithm> and <utility> includes in delaunay_triangulation.cpp.\n\n'
  git -C ~/librcsc diff -- rcsc/geom/delaunay_triangulation.cpp; } > testbed/patches/librcsc/0001-build-fix-missing-includes.patch
{ printf 'Group: build-fix\nReason: GCC 15 rejects the CRTP calls in the bundled simdjson; call through the derived formatter.\n\n'
  git -C ~/librcsc diff -- rcsc/rcg/simdjson/simdjson.h; } > testbed/patches/librcsc/0002-build-fix-simdjson-gcc15.patch
```

- [ ] **Step 4: Write the Cyrus librcsc fork build-fix patches**

Run:
```bash
mkdir -p testbed/patches/cyrus-lib
{ printf 'Group: build-fix\nReason: Boost 1.89 and later have no compiled Boost.System; fall back to the header-only Boost target.\n\n'
  git -C ~/cyrus-soccer-simulation-lib diff -- CMakeLists.txt; } > testbed/patches/cyrus-lib/0001-build-fix-boost-system-header-only.patch
{ printf 'Group: build-fix\nReason: GCC 15 needs an explicit <algorithm> include in param_map.cpp.\n\n'
  git -C ~/cyrus-soccer-simulation-lib diff -- rcsc/param/param_map.cpp; } > testbed/patches/cyrus-lib/0002-build-fix-missing-include.patch
```

- [ ] **Step 5: Write the Cyrus team build-fix patches**

Run:
```bash
mkdir -p testbed/patches/cyrus-team
{ printf 'Group: build-fix\nReason: Boost.System fallback; search the given librcsc with HINTS before /usr/local; find CppDNN and Eigen headers in CYRUS_DEPS_DIR.\n\n'
  git -C ~/cyrus-soccer-simulation-team diff -- CMakeLists.txt; } > testbed/patches/cyrus-team/0001-build-fix-cmake-dependencies.patch
{ printf 'Group: build-fix\nReason: GCC 15 rejects a const-member assignment in the pinned RapidJSON; remove the unused operator before the build.\n\n'
  git -C ~/cyrus-soccer-simulation-team diff -- vendor/rapidjson.cmake
  (cd ~/cyrus-soccer-simulation-team && git diff --no-index -- /dev/null vendor/patch_rapidjson.sh || true); } > testbed/patches/cyrus-team/0002-build-fix-rapidjson-gcc15.patch
grep -n 'new file mode' testbed/patches/cyrus-team/0002-build-fix-rapidjson-gcc15.patch
```
Expected: the `grep` prints one `new file mode 100755` line, and the `+++` line of that file section is `+++ b/vendor/patch_rapidjson.sh`.

- [ ] **Step 6: Check that every patch applies to a clean clone of its pin**

Run:
```bash
check() { # $1 component, $2 url, $3 commit
  rm -rf .testbed/check/$1 && git clone -q "$2" .testbed/check/$1 && git -C .testbed/check/$1 checkout -q "$3"
  for p in testbed/patches/$1/*.patch; do git -C .testbed/check/$1 apply --check "$PWD/$p" && echo "ok $p"; done
}
check librcsc https://github.com/helios-base/librcsc.git 65e139327751f2f45d9b5a03b1f59fb5ca700cd2
check cyrus-lib https://github.com/Cyrus2D/cyrus-soccer-simulation-lib.git 6bafd9b9241a11c3149d449a2b8d8c04fc13f31e
check cyrus-team https://github.com/naderzare/cyrus-soccer-simulation-team.git 335497b715770af427e1b0fbaba3f4290b406c3f
```
Expected: one `ok …` line per patch file (6 lines). A failure means the local diff was made against a different commit: report to the controller.

- [ ] **Step 7: Write the rcssserver seed patch**

Run:
```bash
S=.testbed/check/rcssserver-19.0.0
G="git -C $S -c user.name=matchlab -c user.email=matchlab@localhost"
$G init -q && $G add -A && $G commit -q -m "release tarball"
for p in testbed/patches/rcssserver/*.patch; do [ -e "$p" ] && $G apply "$PWD/$p"; done
$G add -A && $G commit -q -m "build fixes" --allow-empty
grep -n 'addParam( "random_seed"' $S/src/serverparam.cpp
sed -i 's|^    // addParam( "random_seed", M_random_seed, "", 999 );|    addParam( "random_seed", M_random_seed, "", 999 );|' $S/src/serverparam.cpp
N=$(printf '%04d' $(( $(ls testbed/patches/rcssserver/*.patch 2>/dev/null | wc -l) + 1 )))
mkdir -p testbed/patches/rcssserver
{ printf 'Group: seed\nReason: Register server::random_seed again, so a given seed fixes the simulator random numbers (stadium.cpp already uses it when it is 0 or more).\n\n'
  $G diff -- src/serverparam.cpp; } > testbed/patches/rcssserver/$N-seed-random-seed-param.patch
$G checkout -- src/serverparam.cpp
grep -c '^+    addParam( "random_seed", M_random_seed, "", 999 );' testbed/patches/rcssserver/$N-seed-random-seed-param.patch
```
Expected: the first `grep` prints line 962 with `// addParam( "random_seed"`; the last `grep` prints `1` (the patch is not empty).

- [ ] **Step 8: Write the librcsc seed patch**

In `.testbed/check/librcsc` (the clean clone from Step 6), edit `rcsc/random.h`:

1. After `#include <random>`, add:
```cpp
#include <cstdint>
#include <cstdlib>
```
2. Before `class RandomEngine {`, add:
```cpp
/*!
  \brief return the seed in the environment variable RCSC_RANDOM_SEED, or the fallback.
  \param fallback the seed to use when the variable is not set or not a decimal number.
  \return seed value

  matchlab: a fixed seed makes testbed matches reproducible. Without the
  variable, the behaviour is the upstream behaviour.
*/
inline
std::uint32_t
seed_from_env_or( const std::uint32_t fallback )
{
    const char * env = std::getenv( "RCSC_RANDOM_SEED" );
    if ( env && *env )
    {
        char * end = nullptr;
        const unsigned long value = std::strtoul( env, &end, 10 );
        if ( end && *end == '\0' )
        {
            return static_cast< std::uint32_t >( value );
        }
    }
    return fallback;
}
```
3. Replace the constructor initializer `: M_engine( std::random_device()() )` with:
```cpp
        : M_engine( seed_from_env_or( std::random_device()() ) )
```

Edit `rcsc/ann/rbf.cpp` and `rcsc/ann/ngnet.cpp`: add `#include <rcsc/random.h>` after the existing includes, and replace the active line
```cpp
    static std::mt19937 s_engine( std::time( 0 ) );
```
with
```cpp
    static std::mt19937 s_engine( rcsc::seed_from_env_or( static_cast< std::uint32_t >( std::time( 0 ) ) ) );
```

Then run:
```bash
S=.testbed/check/librcsc
{ printf 'Group: seed\nReason: Seed RandomEngine and the ANN engines from RCSC_RANDOM_SEED when it is set; keep the upstream seeds otherwise.\n\n'
  git -C $S diff -- rcsc/random.h rcsc/ann/rbf.cpp rcsc/ann/ngnet.cpp; } > testbed/patches/librcsc/0003-seed-env-random-seed.patch
git -C $S checkout -- rcsc/random.h rcsc/ann/rbf.cpp rcsc/ann/ngnet.cpp
```

- [ ] **Step 9: Write the Cyrus librcsc fork seed patch**

Run:
```bash
S=.testbed/check/cyrus-lib
cp testbed/patches/librcsc/0003-seed-env-random-seed.patch testbed/patches/cyrus-lib/0003-seed-env-random-seed.patch
git -C $S apply --check "$PWD/testbed/patches/cyrus-lib/0003-seed-env-random-seed.patch" && echo APPLIES
```
Expected: `APPLIES`. If it does not apply, make the same three edits in `.testbed/check/cyrus-lib` by hand and write the patch with `git -C $S diff`, as in Step 8. Record the outcome ("same patch applies" or "own patch") in `design.md` Open Questions, row "Is Cyrus seeding worth extra patches…" (Owner column: "Patch written in Task 4: <outcome>; checked in Task 7").

- [ ] **Step 10: Check every patch, in order, on the clean trees**

Run:
```bash
for c in librcsc cyrus-lib cyrus-team; do
  git -C .testbed/check/$c checkout -q . && git -C .testbed/check/$c clean -qfd
  for p in testbed/patches/$c/*.patch; do git -C .testbed/check/$c apply "$PWD/$p" && echo "ok $p"; done
  git -C .testbed/check/$c checkout -q . && git -C .testbed/check/$c clean -qfd
done
harness/.venv/bin/python -c "from matchlab.patches import list_patches; from pathlib import Path; [print(c, p.path.name, p.group) for c in ('rcssserver','librcsc','cyrus-lib','cyrus-team') for p in list_patches(Path('testbed/patches')/c)]"
```
Expected: one `ok …` line per patch of the three git components (all apply in sequence), and the loader lists every patch: groups `build-fix` and `seed`, with `seed` patches numbered after the `build-fix` patches of the same component.

- [ ] **Step 11: Commit**

```bash
git add testbed/patches openspec/changes/add-match-lab-testbed/design.md
git commit -m "feat(testbed): add build-fix and seed patches for the pinned components" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Build command and manifest

**Covers:** tasks.md 2.5, 2.6

**Files:**
- Create: `harness/src/matchlab/manifest.py`, `harness/src/matchlab/build.py`, `harness/tests/test_manifest.py`, `harness/tests/test_build.py`

**Interfaces:**
- Consumes: `Pin`, `COMPONENTS` (Task 2); `list_patches`, `apply_patches`, `patch_checksum` (Task 3); `paths.patches_dir`, `paths.manifest_path` (Task 1).
- Produces:
  - `manifest.py`: `MANIFEST_SCHEMA = 1`; `class ManifestError(RuntimeError)`; `@dataclass(frozen=True) class TeamEntry(start: Path, lib_dirs: tuple[Path, ...])`; `@dataclass(frozen=True) class Manifest(components: dict[str, dict], rcssserver: Path, rcssserver_lib_dirs: tuple[Path, ...], rcg2data: Path, rcg2data_lib_dirs: tuple[Path, ...], teams: dict[str, TeamEntry])` with method `pins() -> dict[str, str]` (component name → ref); `write_manifest(manifest: Manifest, path: Path) -> None`; `load_manifest(path: Path | None = None) -> Manifest`.
  - `build.py`: `class BuildError(RuntimeError)`; `@dataclass(frozen=True) class BuildContext(repo: Path, work: Path, jobs: int = 2)` with properties `src`, `prefix`, `logs`, `downloads`, `patches`; `RECIPES: dict[str, list[list[str]]]`; `HEADER_COPIES`; `fetch(pin: Pin, dest: Path, ctx: BuildContext, log: Path) -> None`; `build_component(name: str, pin: Pin, ctx: BuildContext) -> dict`; `binaries(ctx: BuildContext) -> dict`; `build_all(ctx: BuildContext, pins: dict[str, Pin], only: Sequence[str] | None = None) -> Manifest`.

- [ ] **Step 1: Write the failing manifest tests `harness/tests/test_manifest.py`**

```python
from pathlib import Path

import pytest

from matchlab.manifest import Manifest, ManifestError, TeamEntry, load_manifest, write_manifest


def sample(tmp_path):
    return Manifest(
        components={"librcsc": {"url": "u", "ref": "r", "patches": []}},
        rcssserver=tmp_path / "bin" / "rcssserver",
        rcssserver_lib_dirs=(tmp_path / "lib",),
        rcg2data=tmp_path / "rcg2data",
        rcg2data_lib_dirs=(),
        teams={"helios": TeamEntry(start=tmp_path / "start.sh", lib_dirs=(tmp_path / "lib",))},
    )


def test_round_trip(tmp_path):
    path = tmp_path / "manifest.json"
    write_manifest(sample(tmp_path), path)
    assert load_manifest(path) == sample(tmp_path)
    assert load_manifest(path).pins() == {"librcsc": "r"}


def test_missing_manifest_is_clear(tmp_path):
    with pytest.raises(ManifestError, match="Run `matchlab build` first"):
        load_manifest(tmp_path / "nope.json")
```

- [ ] **Step 2: Run them to see them fail, then write `harness/src/matchlab/manifest.py`**

Run: `harness/.venv/bin/pytest harness/tests/test_manifest.py -q` → FAIL (`ModuleNotFoundError`).

```python
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
```

Run: `harness/.venv/bin/pytest harness/tests/test_manifest.py -q` → `2 passed`.

- [ ] **Step 3: Write the failing build tests `harness/tests/test_build.py`**

These tests use only local files (no network).

```python
import hashlib
import subprocess
import tarfile

import pytest

from matchlab.build import RECIPES, BuildContext, BuildError, _fmt, fetch
from matchlab.pins import Pin


def ctx(tmp_path):
    return BuildContext(repo=tmp_path, work=tmp_path / ".testbed", jobs=3)


def test_cmake_recipes_point_at_their_own_librcsc(tmp_path):
    c = ctx(tmp_path)
    team = " ".join(" ".join(_fmt(cmd, c)) for cmd in RECIPES["cyrus-team"])
    rcg = " ".join(" ".join(_fmt(cmd, c)) for cmd in RECIPES["rcg2data"])
    assert f"-DLIBRCSC_LIB={c.prefix}/cyrus-lib/lib/librcsc.so" in team
    assert f"-DCYRUS_DEPS_DIR={c.prefix}/cyrus-deps" in team
    assert f"-DLIBRCSC_LIB={c.prefix}/librcsc/lib/librcsc.so" in rcg
    assert "-j3" in " ".join(_fmt(RECIPES["librcsc"][2], c))


def make_tarball(tmp_path):
    src = tmp_path / "pkg-1.0"
    src.mkdir()
    (src / "README").write_text("hello\n")
    archive = tmp_path / "pkg-1.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname="pkg-1.0")
    return archive


def test_tarball_checksum_mismatch_names_component(tmp_path):
    archive = make_tarball(tmp_path)
    pin = Pin("demo", "tarball", archive.as_uri(), sha256="0" * 64, strip="pkg-1.0")
    c = ctx(tmp_path)
    log = tmp_path / "log"
    with pytest.raises(BuildError, match="demo: SHA-256 mismatch"):
        fetch(pin, c.src / "demo", c, log)


def test_tarball_is_extracted_into_a_git_tree(tmp_path):
    archive = make_tarball(tmp_path)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    pin = Pin("demo", "tarball", archive.as_uri(), sha256=digest, strip="pkg-1.0")
    c = ctx(tmp_path)
    dest = c.src / "demo"
    fetch(pin, dest, c, tmp_path / "log")
    assert (dest / "README").read_text() == "hello\n"
    assert (dest / ".git").is_dir()


def test_git_pin_checks_out_exact_commit(tmp_path):
    upstream = tmp_path / "up"
    upstream.mkdir()
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*g, "init", "-q"], cwd=upstream, check=True)
    (upstream / "f").write_text("v1\n")
    subprocess.run([*g, "add", "f"], cwd=upstream, check=True)
    subprocess.run([*g, "commit", "-q", "-m", "v1"], cwd=upstream, check=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=upstream, check=True, capture_output=True,
                            text=True).stdout.strip()
    (upstream / "f").write_text("v2\n")
    subprocess.run([*g, "commit", "-q", "-am", "v2"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "uploadpack.allowReachableSHA1InWant", "true"], cwd=upstream, check=True)
    pin = Pin("demo", "git", upstream.as_uri(), commit=commit)
    c = ctx(tmp_path)
    fetch(pin, c.src / "demo", c, tmp_path / "log")
    assert (c.src / "demo" / "f").read_text() == "v1\n"
```

Run: `harness/.venv/bin/pytest harness/tests/test_build.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Write `harness/src/matchlab/build.py`**

```python
"""Fetch, patch and build the pinned testbed components into .testbed/."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tarfile
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, ManifestError, TeamEntry, load_manifest, write_manifest
from .patches import apply_patches, list_patches, patch_checksum
from .pins import COMPONENTS, Pin

_GIT_ID = ["-c", "user.name=matchlab", "-c", "user.email=matchlab@localhost"]


class BuildError(RuntimeError):
    """A testbed component could not be fetched or built."""


@dataclass(frozen=True)
class BuildContext:
    repo: Path
    work: Path
    jobs: int = 2

    @property
    def src(self) -> Path:
        return self.work / "src"

    @property
    def prefix(self) -> Path:
        return self.work / "install"

    @property
    def logs(self) -> Path:
        return self.work / "logs"

    @property
    def downloads(self) -> Path:
        return self.work / "downloads"

    @property
    def patches(self) -> Path:
        return self.repo / "testbed" / "patches"


# Autotools for rcssserver, librcsc and helios-base: their CMake files need the
# compiled Boost.System library, which Boost 1.89 and later no longer ship.
# CMake builds get LIBRCSC_LIB/LIBRCSC_INCLUDE_DIR directly, so find_library
# never picks the librcsc in /usr/local.
RECIPES: dict[str, list[list[str]]] = {
    "rcssserver": [
        ["./configure", "--prefix={prefix}/rcssserver"],
        ["make", "-j{jobs}"],
        ["make", "install"],
    ],
    "librcsc": [
        ["sh", "./bootstrap"],
        ["./configure", "--prefix={prefix}/librcsc", "--disable-unit-test"],
        ["make", "-j{jobs}"],
        ["make", "install"],
    ],
    "helios-base": [
        ["sh", "./bootstrap"],
        ["./configure", "--with-librcsc={prefix}/librcsc"],
        ["make", "-j{jobs}"],
    ],
    "cyrus-lib": [
        ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release",
         "-DCMAKE_INSTALL_PREFIX={prefix}/cyrus-lib"],
        ["cmake", "--build", "build", "-j{jobs}"],
        ["cmake", "--install", "build"],
    ],
    "cyrus-team": [
        ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release",
         "-DLIBRCSC_INSTALL_DIR={prefix}/cyrus-lib",
         "-DLIBRCSC_LIB={prefix}/cyrus-lib/lib/librcsc.so",
         "-DLIBRCSC_INCLUDE_DIR={prefix}/cyrus-lib/include",
         "-DCYRUS_DEPS_DIR={prefix}/cyrus-deps"],
        ["cmake", "--build", "build", "-j{jobs}"],
    ],
    "rcg2data": [
        ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release",
         "-DLIBRCSC_LIB={prefix}/librcsc/lib/librcsc.so",
         "-DLIBRCSC_INCLUDE_DIR={prefix}/librcsc/include"],
        ["cmake", "--build", "build", "-j{jobs}"],
    ],
}

# (source folder in the component, destination under the prefix, glob or None for a whole tree)
HEADER_COPIES: dict[str, list[tuple[str, str, str | None]]] = {
    "cppdnn": [("src", "cyrus-deps/include/CppDNN", "*.h")],
    "eigen": [
        ("Eigen", "cyrus-deps/include/eigen3/Eigen", None),
        ("unsupported", "cyrus-deps/include/eigen3/unsupported", None),
    ],
}


def _fmt(cmd: list[str], ctx: BuildContext) -> list[str]:
    return [part.format(prefix=ctx.prefix, jobs=ctx.jobs) for part in cmd]


def _run(cmd: Sequence[object], cwd: Path, log: Path) -> None:
    args = [str(c) for c in cmd]
    with log.open("a") as fh:
        fh.write(f"$ {' '.join(args)}\n")
        fh.flush()
        result = subprocess.run(args, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise BuildError(f"command failed with exit code {result.returncode}: {' '.join(args)}; see {log}")


def fetch(pin: Pin, dest: Path, ctx: BuildContext, log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if pin.kind == "git":
        dest.mkdir()
        _run(["git", "init", "-q"], dest, log)
        _run(["git", "remote", "add", "origin", pin.url], dest, log)
        ref = pin.commit if pin.commit else f"refs/tags/{pin.tag}"
        _run(["git", "fetch", "-q", "--depth", "1", "origin", ref], dest, log)
        _run(["git", "checkout", "-q", "FETCH_HEAD"], dest, log)
        return
    ctx.downloads.mkdir(parents=True, exist_ok=True)
    archive = ctx.downloads / pin.url.rsplit("/", 1)[-1]
    if not archive.exists():
        urllib.request.urlretrieve(pin.url, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != pin.sha256:
        archive.unlink()
        raise BuildError(f"{pin.name}: SHA-256 mismatch for {archive.name}: expected {pin.sha256}, got {digest}")
    tmp = dest.parent / f".{dest.name}.extract"
    if tmp.exists():
        shutil.rmtree(tmp)
    with tarfile.open(archive) as tar:
        tar.extractall(tmp, filter="data")
    (tmp / pin.strip).rename(dest)
    shutil.rmtree(tmp)
    # git apply needs its own repository here; otherwise it resolves paths
    # against the enclosing project repository.
    _run(["git", "init", "-q"], dest, log)
    _run(["git", "add", "-A"], dest, log)
    _run(["git", *_GIT_ID, "commit", "-q", "-m", "release tarball"], dest, log)


def _copy_headers(name: str, src_dir: Path, ctx: BuildContext) -> None:
    for rel_src, rel_dst, pattern in HEADER_COPIES[name]:
        dst = ctx.prefix / rel_dst
        if dst.exists():
            shutil.rmtree(dst)
        if pattern is None:
            shutil.copytree(src_dir / rel_src, dst)
        else:
            dst.mkdir(parents=True)
            for header in sorted((src_dir / rel_src).glob(pattern)):
                shutil.copy2(header, dst / header.name)


def build_component(name: str, pin: Pin, ctx: BuildContext) -> dict:
    ctx.logs.mkdir(parents=True, exist_ok=True)
    log = ctx.logs / f"{name}.log"
    log.write_text("")
    dest = ctx.src / name
    fetch(pin, dest, ctx, log)
    patches = list_patches(ctx.patches / name)
    apply_patches(dest, name, patches)
    if name in HEADER_COPIES:
        _copy_headers(name, dest, ctx)
    else:
        install = ctx.prefix / name
        if install.exists():
            shutil.rmtree(install)
        for cmd in RECIPES[name]:
            _run(_fmt(cmd, ctx), dest, log)
    return {
        "url": pin.url,
        "ref": pin.ref,
        "patches": [{"file": p.path.name, "group": p.group, "sha256": patch_checksum(p)} for p in patches],
    }


def binaries(ctx: BuildContext) -> dict:
    return {
        "rcssserver": (ctx.prefix / "rcssserver/bin/rcssserver", (ctx.prefix / "rcssserver/lib",)),
        "rcg2data": (ctx.src / "rcg2data/build/src/rcg2data", (ctx.prefix / "librcsc/lib",)),
        "teams": {
            "helios": TeamEntry(ctx.src / "helios-base/src/start.sh", (ctx.prefix / "librcsc/lib",)),
            "cyrus": TeamEntry(ctx.src / "cyrus-team/build/src/start.sh", (ctx.prefix / "cyrus-lib/lib",)),
        },
    }


def build_all(ctx: BuildContext, pins: dict[str, Pin], only: Sequence[str] | None = None) -> Manifest:
    names = list(only) if only else list(COMPONENTS)
    unknown = sorted(set(names) - set(COMPONENTS))
    if unknown:
        raise BuildError(f"unknown component(s): {', '.join(unknown)}")
    components: dict[str, dict] = {}
    if only:
        try:
            components = dict(load_manifest(ctx.work / "manifest.json").components)
        except ManifestError as exc:
            raise BuildError("a partial build needs an earlier full build; run `matchlab build` first") from exc
    for name in COMPONENTS:
        if name in names:
            components[name] = build_component(name, pins[name], ctx)
    bins = binaries(ctx)
    manifest = Manifest(
        components=components,
        rcssserver=bins["rcssserver"][0],
        rcssserver_lib_dirs=bins["rcssserver"][1],
        rcg2data=bins["rcg2data"][0],
        rcg2data_lib_dirs=bins["rcg2data"][1],
        teams=bins["teams"],
    )
    expected = [manifest.rcssserver, manifest.rcg2data, *(t.start for t in manifest.teams.values())]
    missing = [str(p) for p in expected if not p.exists()]
    if missing:
        raise BuildError(f"build finished but these files are missing: {', '.join(missing)}")
    write_manifest(manifest, ctx.work / "manifest.json")
    return manifest
```

- [ ] **Step 5: Run the build and manifest tests**

Run: `harness/.venv/bin/pytest harness/tests/test_build.py harness/tests/test_manifest.py -q`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add harness/src/matchlab/build.py harness/src/matchlab/manifest.py harness/tests/test_build.py harness/tests/test_manifest.py
git commit -m "feat(testbed): fetch, patch and build pinned components and write a manifest" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: One full build in the apply worktree

**Covers:** tasks.md 2.7 (the `build` subcommand of 8.1 is written here; 8.1 is checked off in Task 17)

**Files:**
- Create: `harness/src/matchlab/cli.py` (build subcommand only; Task 17 adds the rest)
- Modify: patches only if the real build exposes a defect (add a numbered `build-fix` patch with a `Reason:` line; never edit sources in `.testbed/src` by hand)

**Interfaces:**
- Consumes: `build_all`, `BuildContext`, `load_pins`, `paths`; all build-fix and seed patches from Task 4.
- Produces: `matchlab.cli.main(argv: Sequence[str] | None = None) -> int` with the `build` subcommand (`--jobs N`, `--only COMPONENT...`); a built testbed in `.testbed/` with `.testbed/manifest.json`.

The apply worktree is a fresh checkout: only `.testbed/check/` (Task 4) exists, and `.testbed/src/` and `.testbed/install/` do not. So one build here proves the fresh-checkout requirement. Do not clone the repository again.

- [ ] **Step 1: Write a minimal `harness/src/matchlab/cli.py` with the build subcommand**

```python
"""Command-line interface: matchlab build | run | experiment | check-repro."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import paths
from .build import BuildContext, BuildError, build_all
from .manifest import ManifestError
from .patches import PatchError
from .pins import COMPONENTS, PinError, load_pins


def _cmd_build(args: argparse.Namespace) -> int:
    ctx = BuildContext(repo=paths.repo_root(), work=paths.work_dir(), jobs=args.jobs)
    manifest = build_all(ctx, load_pins(paths.testbed_dir() / "pins.toml"), only=args.only)
    print(f"Testbed built. Manifest: {paths.manifest_path()}")
    for name, team in sorted(manifest.teams.items()):
        print(f"  team {name}: {team.start}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matchlab", description="Build the RoboCup testbed and run experiments.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="fetch, patch and build the pinned testbed into .testbed/")
    build.add_argument("--jobs", type=int, default=2, help="parallel compile jobs (default 2; 3 GB RAM)")
    build.add_argument("--only", nargs="+", choices=COMPONENTS, help="rebuild only these components")
    build.set_defaults(handler=_cmd_build)
    return parser


ERRORS: tuple[type[Exception], ...] = (PinError, PatchError, BuildError, ManifestError)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Commit the CLI, so the working tree is clean before the build**

```bash
git add harness/src/matchlab/cli.py
git commit -m "feat(harness): add the matchlab build command" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --porcelain
```
Expected: `git status --porcelain` prints nothing.

- [ ] **Step 3: Run the full build in the background**

This takes about 30–60 minutes. Run it with the Bash tool's `run_in_background` option, and wait for the completion notice:
```bash
touch /tmp/matchlab-build-marker
harness/.venv/bin/matchlab build --jobs 2 > /tmp/matchlab-build.log 2>&1; echo "exit $?" >> /tmp/matchlab-build.log
```
Then run: `tail -5 /tmp/matchlab-build.log`
Expected: `Testbed built. Manifest: …/.testbed/manifest.json`, two `team` lines, and `exit 0`. If a component fails, read `.testbed/logs/<component>.log`. Fix it with a numbered `Group: build-fix` patch, commit it, and run Step 3 again.

- [ ] **Step 4: Check library linking**

Run:
```bash
P=.testbed/install
LD_LIBRARY_PATH=$P/librcsc/lib ldd .testbed/src/helios-base/src/sample_player | grep rcsc
LD_LIBRARY_PATH=$P/cyrus-lib/lib ldd .testbed/src/cyrus-team/build/src/sample_player | grep rcsc
LD_LIBRARY_PATH=$P/librcsc/lib ldd .testbed/src/rcg2data/build/src/rcg2data | grep rcsc
grep -n '^LIBPATH=' .testbed/src/helios-base/src/start.sh .testbed/src/cyrus-team/build/src/start.sh
```
Expected: HELIOS and rcg2data resolve `librcsc.so` under `.testbed/install/librcsc/lib`; Cyrus resolves it under `.testbed/install/cyrus-lib/lib`; the two `LIBPATH=` lines point at those same folders. No line points at `/usr/local/lib`.

- [ ] **Step 5: Check that nothing outside `.testbed/` changed**

Run:
```bash
git status --porcelain
find ~/.local/lib ~/.local/include ~/.local/bin ~/local /usr/local -maxdepth 3 -newer /tmp/matchlab-build-marker 2>/dev/null | head
```
Expected: no output from either command.

- [ ] **Step 6: Commit new build-fix patches (only if Step 3 needed any)**

```bash
git add testbed/patches
git commit -m "fix(testbed): build-fix patches found by the full build" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Seed behaviour checks

**Covers:** tasks.md 3.1, 3.2, 3.3 (the patches were written in Task 4 and built in Task 6)

**Files:**
- Modify: `openspec/changes/add-match-lab-testbed/design.md` (Open Questions row about Cyrus seeding, if Task 4 did not fill it)

**Interfaces:**
- Consumes: the built testbed from Task 6.
- Produces: evidence that rcssserver accepts `server::random_seed` and that both librcsc copies seed from `RCSC_RANDOM_SEED`, with upstream behaviour when no seed is given.

- [ ] **Step 1: Check the server seed and the no-seed behaviour**

Run:
```bash
B=.testbed/install/rcssserver/bin/rcssserver
mkdir -p .testbed/check/home
HOME=$PWD/.testbed/check/home timeout 5 $B server::port=16090 server::coach_port=16091 server::olcoach_port=16092 server::random_seed=42 2>&1 | grep -i seed || true
HOME=$PWD/.testbed/check/home timeout 5 $B server::port=16090 server::coach_port=16091 server::olcoach_port=16092 2>&1 | grep -i seed || true
```
Expected: the first run prints `Using given Simulator Random Seed: 42`; the second prints `Simulator Random Seed: <clock value>` (upstream behaviour).

- [ ] **Step 2: Check the client seed path of both librcsc copies**

Run:
```bash
cat > .testbed/check/seed.cpp <<'EOF'
#include <rcsc/random.h>
#include <iostream>
int main() { std::cout << rcsc::RandomEngine::instance().get()() << "\n"; }
EOF
for lib in librcsc cyrus-lib; do
  g++ -std=c++17 -I.testbed/install/$lib/include .testbed/check/seed.cpp -o .testbed/check/seed-$lib
  echo "$lib:"; RCSC_RANDOM_SEED=7 .testbed/check/seed-$lib; RCSC_RANDOM_SEED=7 .testbed/check/seed-$lib
  .testbed/check/seed-$lib; .testbed/check/seed-$lib
done
```
Expected, for each library: the two `RCSC_RANDOM_SEED=7` lines are equal, and the two lines without the variable differ. `RandomEngine::get()` returns the `std::mt19937` engine. If the Cyrus seed patch was not applied (see the Task 4 record), its lines without and with the variable all differ: record that.

- [ ] **Step 3: Record the Cyrus outcome and commit (only if `design.md` changed)**

Make sure the Open Questions row "Is Cyrus seeding worth extra patches…" states the outcome from Task 4 and Step 2.

```bash
git add openspec/changes/add-match-lab-testbed/design.md
git commit -m "docs(change): record the seed patch checks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Reproducibility spike (checkpoint with the user)

**Covers:** tasks.md 3.4, 3.5

**Files:**
- Create (throwaway, ignored): `.testbed/spike/spike.sh`
- Modify: `openspec/changes/add-match-lab-testbed/design.md` (D5 and Open Questions)

**Interfaces:**
- Produces: a decision recorded in `design.md`: the `identical` path or fallback B; the coach default (on, or off if coaches cause divergence); and the list of line prefixes (if any) that the check must skip (`SKIP_PREFIXES` in Task 12).

The spike reproduces what the harness will do: synch mode, a huge `connect_wait`, `kick_off_wait` 300, and team-by-team connection gating on the server log.

- [ ] **Step 1: Write the spike script `.testbed/spike/spike.sh`**

```bash
#!/usr/bin/env bash
# Throwaway spike: run HELIOS vs HELIOS twice with the same seeds and compare the game logs.
set -uo pipefail
T="$(cd "$(dirname "$0")/.." && pwd)"
SERVER="$T/install/rcssserver/bin/rcssserver"
START="$T/src/helios-base/src/start.sh"   # absolute path: the player command lines then contain it
COACH_OPT="${COACH_OPT:-}"                 # set COACH_OPT=-C to run without coaches

wait_team() { # $1 server log, $2 team name: wait for 11 players and, with coaches, the coach
  local p=0 c=0
  for _ in $(seq 600); do
    p=$(grep -c "player ($2 [0-9]*) connected" "$1")
    c=$(grep -c "online coach ($2) connected" "$1")
    if [ "$p" -ge 11 ] && { [ -n "$COACH_OPT" ] || [ "$c" -ge 1 ]; }; then return 0; fi
    sleep 0.1
  done
  echo "team $2 did not connect ($p players, $c coach)"; return 1
}

for run in a b; do
  D="$T/spike/$run"; rm -rf "$D"; mkdir -p "$D/home"
  HOME="$D/home" LD_LIBRARY_PATH="$T/install/rcssserver/lib" "$SERVER" \
    server::port=16000 server::coach_port=16001 server::olcoach_port=16002 \
    server::synch_mode=true server::auto_mode=true server::random_seed=737161366 \
    server::connect_wait=100000000 server::kick_off_wait=300 \
    server::half_time=30 server::nr_normal_halfs=2 server::nr_extra_halfs=0 server::penalty_shoot_outs=false \
    server::game_log_dir="$D" server::text_log_dir="$D" server::game_log_fixed=true server::text_log_fixed=true \
    server::game_log_fixed_name=match server::text_log_fixed_name=match \
    server::game_log_compression=0 server::text_log_compression=0 > "$D/server.log" 2>&1 &
  S=$!
  sleep 1
  RCSC_RANDOM_SEED=1608858898 "$START" -h 127.0.0.1 -p 16000 -P 16002 -t HELIOS_L $COACH_OPT > "$D/left.log" 2>&1
  wait_team "$D/server.log" HELIOS_L
  RCSC_RANDOM_SEED=308656577 "$START" -h 127.0.0.1 -p 16000 -P 16002 -t HELIOS_R $COACH_OPT > "$D/right.log" 2>&1
  wait_team "$D/server.log" HELIOS_R
  timeout 900 tail --pid=$S -f /dev/null || { echo "run $run: server still running after 900 s"; kill $S; }
  pkill -f "$T/src/helios-base/src/sample_" || true
  echo "run $run: missed cycles: $(grep -c 'Someone missed a cycle' "$D/server.log")"
  sleep 1
done
if cmp -s "$T/spike/a/match.rcg" "$T/spike/b/match.rcg"; then
  echo IDENTICAL
else
  echo DIFFERS
  cmp "$T/spike/a/match.rcg" "$T/spike/b/match.rcg" | head -1
  diff "$T/spike/a/match.rcg" "$T/spike/b/match.rcg" | head -20
fi
```

The team seeds are `team_seed(737161366, "left")` and `team_seed(737161366, "right")` from Task 10, so the spike uses the same seeds as harness match 0 of base seed 42.

- [ ] **Step 2: Run the spike (about 5–10 minutes; run it in the background)**

Run: `bash .testbed/spike/spike.sh > .testbed/spike/result.txt 2>&1` with the Bash tool's `run_in_background` option, wait for it, then `cat .testbed/spike/result.txt`.
Expected: two `missed cycles` lines, then `IDENTICAL` or `DIFFERS` followed by the first differing line. Also check: `.testbed/spike/a/server.log` contains `Using given Simulator Random Seed: 737161366`; each `match.rcg` has a final `(team 600 …)` line (the match finished); both coaches connected (`grep -c "online coach" .testbed/spike/a/server.log` prints `2`).

- [ ] **Step 3: If the result is DIFFERS, classify the first difference**

Read the first differing lines. Classify them as one of:
- (a) a non-match field (for example a header or version line that holds a time stamp). Note its line prefix; the check may skip it.
- (b) a play difference (`(show …` lines differ). Note the first cycle and whether `missed cycles` was above 0 in either run.
- (c) the match did not finish (synch mode stalled, or a team did not connect). Note what the server log says.

For (a), re-run the comparison with that prefix skipped (`grep -v '^<prefix>'` on both files, then `cmp`) to see whether the rest is identical. For (b) without missed cycles, run the spike once more with `COACH_OPT=-C bash .testbed/spike/spike.sh` (in the background) to see whether the coaches cause the difference.

- [ ] **Step 4: Record the result in `design.md`**

In D5, add a line `- **Spike result (Task 8)**: <IDENTICAL | DIFFERS: class (a)/(b)/(c), first cycle N, missed cycles a/b, coach-off result, skipped prefixes [...]>`. In Open Questions, set the Owner column of the rows "Do synch mode and seeds give byte-identical `.rcg` files…" and "Do coaches connect before kick-off in every run?" to `Spike done: <result>`.

- [ ] **Step 5: CHECKPOINT. Stop and report to the controller**

Report the spike result, the classification, the coach-off result (if run) and the proposed `SKIP_PREFIXES` value (empty tuple if none). **The controller asks the user** to choose:
- the `identical` path (only possible with IDENTICAL, or with class (a) and an approved skip list) or fallback B (statistical reproducibility);
- the coach default: stays on, or changes to off (only if the coach-off run is identical and the coach-on runs are not).

Do not continue with Task 9 before the controller confirms. Record the decisions in `design.md` Open Questions as `Decided by user on <date>: <decision>`. If the coach default changes to off, Task 9 changes the `coach` default in `_teams` from `True` to `False` and the test `test_default_preset_resolves` to expect `"coach": False`.

- [ ] **Step 6: Commit**

```bash
git add openspec/changes/add-match-lab-testbed/design.md
git commit -m "docs(change): record the reproducibility spike result and decisions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Profiles and presets

**Covers:** tasks.md 4.1, 4.2, 4.3

**Before you start:** read the Task 8 decision in `design.md` Open Questions ("Do coaches connect before kick-off in every run?"). If the user decided **coach off**, use `coach = entry.get("coach", False)` in `_teams`, and expect `"coach": False` in `test_default_preset_resolves`. Otherwise keep the code below as it is (`True`).

**Files:**
- Create: `harness/src/matchlab/profile.py`, `harness/tests/test_profile.py`, `testbed/profiles/default.toml`, `testbed/profiles/noise-off.toml`, `testbed/profiles/short.toml`
- Delete: `testbed/profiles/.gitkeep`

**Interfaces:**
- Consumes: `paths.profiles_dir()`.
- Produces: `SIDES = ("left", "right")`; `NOISE_PARAMS: tuple[str, ...]`; `PLAYER_NOISE_PARAMS: tuple[str, ...]`; `RESERVED_SERVER: frozenset[str]`; `class ProfileError(ValueError)`; `profile_hash(data: dict) -> str`; `@dataclass(frozen=True) class Profile(data: dict)` with property `hash -> str`, property `cycles -> int`, `team(side: str) -> dict`, `swapped() -> Profile`; `load_profile(ref: str | Path, *, overrides: dict | None = None, known_teams: Collection[str] | None = None, base_dir: Path | None = None) -> Profile`.

Resolved profile shape (`Profile.data`):
```python
{
  "match": {"halves": 2, "half_time": 300},
  "server": {"nr_extra_halfs": 0, "penalty_shoot_outs": False, ...},
  "player": {...},
  "teams": {"left": {"team": "helios", "name": "HELIOS_L", "coach": True},
            "right": {"team": "helios", "name": "HELIOS_R", "coach": True}},
}
```

- [ ] **Step 1: Write the presets**

`testbed/profiles/default.toml`:
```toml
# Upstream rcssserver 19.0.0 values, with one change: a draw ends the match
# after normal time (no extra time, no penalty shoot-out).
[match]
halves = 2
half_time = 300   # seconds of match time per half; 300 s = 3000 cycles

[server]
nr_extra_halfs = 0
penalty_shoot_outs = false

[teams.left]
team = "helios"

[teams.right]
team = "helios"
```

`testbed/profiles/noise-off.toml`:
```toml
# The default profile with every random noise parameter set to 0.
# Quantize steps stay as they are: the server divides by them.
extends = "default"

[server]
ball_rand = 0
player_rand = 0
kick_rand = 0
prand_factor_l = 0
prand_factor_r = 0
kick_rand_factor_l = 0
kick_rand_factor_r = 0
wind_rand = 0
tackle_rand_factor = 0
dist_noise_rate = 0
focus_dist_noise_rate = 0
land_dist_noise_rate = 0
land_focus_dist_noise_rate = 0

[player]
kick_rand_delta_factor = 0
```

`testbed/profiles/short.toml`:
```toml
# A short match for tests: 2 halves of 30 s (600 cycles in total).
extends = "default"

[match]
half_time = 30
```

- [ ] **Step 2: Write the failing tests `harness/tests/test_profile.py`**

```python
import pytest

from matchlab.profile import (NOISE_PARAMS, PLAYER_NOISE_PARAMS, Profile, ProfileError, load_profile,
                              profile_hash)


def write(path, text):
    path.write_text(text)
    return path


def test_default_preset_resolves():
    p = load_profile("default", known_teams={"helios", "cyrus"})
    assert p.data["match"] == {"halves": 2, "half_time": 300}
    assert p.team("left") == {"team": "helios", "name": "HELIOS_L", "coach": True}
    assert p.team("right")["name"] == "HELIOS_R"
    assert p.cycles == 6000


def test_extends_and_override(tmp_path):
    child = write(tmp_path / "child.toml", 'extends = "default"\n[server]\nball_rand = 0\n')
    p = load_profile(child)
    assert p.data["server"]["ball_rand"] == 0
    assert p.data["server"]["nr_extra_halfs"] == 0


def test_equal_values_equal_hash(tmp_path):
    a = write(tmp_path / "a.toml", '[match]\nhalves = 2\nhalf_time = 300\n[server]\nnr_extra_halfs = 0\n'
              'penalty_shoot_outs = false\n[teams.right]\nteam = "helios"\n[teams.left]\nteam = "helios"\n')
    b = write(tmp_path / "b.toml", 'extends = "default"\n[match]\nhalf_time = 300.0\n')
    assert load_profile(a).hash == load_profile(b).hash == load_profile("default").hash


def test_different_values_different_hash():
    assert load_profile("default").hash != load_profile("short").hash
    assert profile_hash({"x": 1}) != profile_hash({"x": 2})


def test_noise_off_zeroes_every_noise_parameter():
    p = load_profile("noise-off")
    assert all(p.data["server"][k] == 0 for k in NOISE_PARAMS)
    assert all(p.data["player"][k] == 0 for k in PLAYER_NOISE_PARAMS)


def test_short_is_at_most_600_cycles():
    assert load_profile("short").cycles <= 600


def test_unknown_team_is_rejected():
    with pytest.raises(ProfileError, match="unknown team 'cyruss'"):
        load_profile("default", overrides={"teams": {"right": {"team": "cyruss"}}}, known_teams={"helios", "cyrus"})


def test_unknown_section_is_rejected(tmp_path):
    with pytest.raises(ProfileError, match="unknown section.*noise"):
        load_profile(write(tmp_path / "x.toml", 'extends = "default"\n[noise]\nball_rand = 0\n'))


@pytest.mark.parametrize("body, message", [
    ('[server]\nball_rand = [0, 1]\n', "server.ball_rand"),
    ('[server]\nfoo = { a = 1 }\n', "server.foo"),
    ('[server]\nlog = "a b"\n', "server.log"),
    ('[server]\nport = 7000\n', "reserved"),
    ('[server]\nhalf_time = 10\n', "reserved"),
    ('[server]\nconnect_wait = 5\n', "server.connect_wait: this parameter is reserved"),
    ('[teams.right]\nname = "HELIOS_L"\n', "names must differ"),
    ('[teams.left]\nname = "this-name-is-far-too-long"\n', "teams.left.name"),
])
def test_rejects_bad_values(tmp_path, body, message):
    with pytest.raises(ProfileError, match=message):
        load_profile(write(tmp_path / "bad.toml", 'extends = "default"\n' + body))


def test_inheritance_loop(tmp_path):
    write(tmp_path / "a.toml", 'extends = "./b.toml"\n')
    write(tmp_path / "b.toml", 'extends = "./a.toml"\n')
    with pytest.raises(ProfileError, match="loop"):
        load_profile(tmp_path / "a.toml")


def test_swapped_exchanges_teams():
    p = load_profile("default", overrides={"teams": {"right": {"team": "cyrus"}}})
    s = p.swapped()
    assert s.team("left")["team"] == "cyrus" and s.team("right")["team"] == "helios"
    assert isinstance(s, Profile)
```

- [ ] **Step 3: Run them to see them fail**

Run: `harness/.venv/bin/pytest harness/tests/test_profile.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Write `harness/src/matchlab/profile.py`**

```python
"""Match profiles: TOML files with inheritance, validation and a stable hash."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import tomllib
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import profiles_dir

SIDES = ("left", "right")
SECTIONS = frozenset({"extends", "match", "server", "player", "teams"})
MATCH_DEFAULTS = {"halves": 2, "half_time": 300}
TEAM_KEYS = frozenset({"team", "name", "coach"})

NOISE_PARAMS: tuple[str, ...] = (
    "ball_rand", "player_rand", "kick_rand",
    "prand_factor_l", "prand_factor_r", "kick_rand_factor_l", "kick_rand_factor_r",
    "wind_rand", "tackle_rand_factor",
    "dist_noise_rate", "focus_dist_noise_rate", "land_dist_noise_rate", "land_focus_dist_noise_rate",
)
PLAYER_NOISE_PARAMS: tuple[str, ...] = ("kick_rand_delta_factor",)

# The harness sets these itself for every match.
RESERVED_SERVER = frozenset({
    "port", "coach_port", "olcoach_port", "synch_mode", "auto_mode", "random_seed",
    "connect_wait", "kick_off_wait", "synch_wait_clients",
    "game_logging", "text_logging", "game_log_dir", "text_log_dir",
    "game_log_fixed", "text_log_fixed", "game_log_fixed_name", "text_log_fixed_name",
    "game_log_compression", "text_log_compression", "game_log_version", "nr_normal_halfs", "half_time",
})
RESERVED_PLAYER = frozenset({"random_seed"})

_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_TEAM_NAME = re.compile(r"^[A-Za-z0-9_-]{1,15}$")


class ProfileError(ValueError):
    """A profile file is missing, malformed or invalid."""


def _canonical(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    return value


def profile_hash(data: dict) -> str:
    text = json.dumps(_canonical(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Profile:
    data: dict

    @property
    def hash(self) -> str:
        return profile_hash(self.data)

    @property
    def cycles(self) -> int:
        step_ms = self.data["server"].get("simulator_step", 100)
        return int(round(self.data["match"]["halves"] * self.data["match"]["half_time"] * 1000 / step_ms))

    def team(self, side: str) -> dict:
        return self.data["teams"][side]

    def swapped(self) -> "Profile":
        data = copy.deepcopy(self.data)
        data["teams"] = {"left": data["teams"]["right"], "right": data["teams"]["left"]}
        return Profile(data)


def _locate(ref: str | Path, base_dir: Path | None) -> Path:
    text = str(ref)
    if text.endswith(".toml") or "/" in text:
        path = Path(text)
        if not path.is_absolute():
            path = (base_dir or Path.cwd()) / path
        return path.resolve()
    return profiles_dir() / f"{text}.toml"


def _merge(base: dict, top: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _load_raw(path: Path, seen: tuple[Path, ...]) -> dict:
    if path in seen:
        chain = " -> ".join(str(p) for p in (*seen, path))
        raise ProfileError(f"profile inheritance loop: {chain}")
    if not path.is_file():
        raise ProfileError(f"profile not found: {path}")
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path.name}: invalid TOML: {exc}") from exc
    unknown = sorted(set(raw) - SECTIONS)
    if unknown:
        raise ProfileError(f"{path.name}: unknown section(s): {', '.join(unknown)}")
    parent = raw.pop("extends", None)
    if parent is None:
        return raw
    return _merge(_load_raw(_locate(parent, path.parent), (*seen, path)), raw)


def _check_scalar(where: str, value: Any) -> None:
    if isinstance(value, (dict, list)):
        raise ProfileError(f"{where}: value must be a number, a boolean or a word, not {type(value).__name__}")
    if isinstance(value, str) and (not value or any(ch.isspace() for ch in value)):
        raise ProfileError(f"{where}: text values must be one word without spaces")


def _params(raw: dict, section: str, reserved: frozenset[str]) -> dict:
    params = raw.get(section, {})
    if not isinstance(params, dict):
        raise ProfileError(f"[{section}] must be a table")
    for key, value in params.items():
        if not _KEY.match(key):
            raise ProfileError(f"{section}.{key}: parameter names use lower case, digits and _")
        if key in reserved:
            raise ProfileError(f"{section}.{key}: this parameter is reserved; the harness sets it")
        _check_scalar(f"{section}.{key}", value)
    return {k: _canonical(v) for k, v in sorted(params.items())}


def _match(raw: dict) -> dict:
    match = {**MATCH_DEFAULTS, **raw.get("match", {})}
    unknown = sorted(set(match) - set(MATCH_DEFAULTS))
    if unknown:
        raise ProfileError(f"[match]: unknown key(s): {', '.join(unknown)}")
    if not isinstance(match["halves"], int) or isinstance(match["halves"], bool) or match["halves"] < 1:
        raise ProfileError("match.halves: must be a whole number of 1 or more")
    if not isinstance(match["half_time"], (int, float)) or isinstance(match["half_time"], bool) \
            or match["half_time"] <= 0:
        raise ProfileError("match.half_time: must be a number of seconds greater than 0")
    return {k: _canonical(v) for k, v in sorted(match.items())}


def _teams(raw: dict, known_teams: Collection[str] | None) -> dict:
    teams = raw.get("teams", {})
    if set(teams) != set(SIDES):
        raise ProfileError("[teams]: set both teams.left and teams.right")
    out = {}
    for side in SIDES:
        entry = teams[side]
        unknown = sorted(set(entry) - TEAM_KEYS)
        if unknown:
            raise ProfileError(f"teams.{side}: unknown key(s): {', '.join(unknown)}")
        team = entry.get("team")
        if not isinstance(team, str) or not team:
            raise ProfileError(f"teams.{side}.team: name a team from the manifest")
        if known_teams is not None and team not in known_teams:
            raise ProfileError(f"teams.{side}: unknown team '{team}'; known teams: {', '.join(sorted(known_teams))}")
        name = entry.get("name", f"{team.upper()}_{side[0].upper()}"[:15])
        if not isinstance(name, str) or not _TEAM_NAME.match(name):
            raise ProfileError(f"teams.{side}.name: use 1 to 15 letters, digits, _ or -")
        coach = entry.get("coach", True)
        if not isinstance(coach, bool):
            raise ProfileError(f"teams.{side}.coach: must be true or false")
        out[side] = {"team": team, "name": name, "coach": coach}
    if out["left"]["name"] == out["right"]["name"]:
        raise ProfileError("teams: the left and right team names must differ")
    return out


def load_profile(ref: str | Path, *, overrides: dict | None = None,
                 known_teams: Collection[str] | None = None, base_dir: Path | None = None) -> Profile:
    raw = _load_raw(_locate(ref, base_dir), ())
    if overrides:
        unknown = sorted(set(overrides) - (SECTIONS - {"extends"}))
        if unknown:
            raise ProfileError(f"overrides: unknown section(s): {', '.join(unknown)}")
        raw = _merge(raw, overrides)
    data = {
        "match": _match(raw),
        "server": _params(raw, "server", RESERVED_SERVER),
        "player": _params(raw, "player", RESERVED_PLAYER),
        "teams": _teams(raw, known_teams),
    }
    return Profile(data)
```

- [ ] **Step 5: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_profile.py -q`
Expected: all pass (`18 passed`).

- [ ] **Step 6: Commit**

```bash
git rm -q --cached testbed/profiles/.gitkeep 2>/dev/null; rm -f testbed/profiles/.gitkeep
git add testbed/profiles harness/src/matchlab/profile.py harness/tests/test_profile.py
git commit -m "feat(harness): TOML match profiles with presets, validation and a stable hash" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Seeds and port slots

**Covers:** tasks.md 5.1, 5.2

**Files:**
- Create: `harness/src/matchlab/seeds.py`, `harness/src/matchlab/ports.py`, `harness/tests/test_seeds.py`, `harness/tests/test_ports.py`

**Interfaces:**
- Produces: `derive_seed(*parts: object) -> int`; `match_seeds(base_seed: int, n: int) -> list[int]`; `team_seed(match_seed: int, side: str) -> int`; `BASE_PORT = 16000`; `STRIDE = 10`; `@dataclass(frozen=True) class PortSet(player: int, coach: int, olcoach: int)`; `class PortInUseError(RuntimeError)`; `port_set(slot: int, base: int = BASE_PORT) -> PortSet`; `ensure_free(ports: PortSet) -> None`; `is_bound(port: int) -> bool` (reads `/proc/net/udp` and `/proc/net/udp6`); `wait_until_bound(port: int, *, timeout_s: float = 10.0, proc: subprocess.Popen | None = None) -> None`.

- [ ] **Step 1: Write the failing tests**

`harness/tests/test_seeds.py`:
```python
from matchlab.seeds import derive_seed, match_seeds, team_seed


def test_fixed_values():
    assert match_seeds(42, 2) == [737161366, 1416715386]
    assert team_seed(737161366, "left") == 1608858898
    assert team_seed(737161366, "right") == 308656577


def test_range_and_stability():
    seeds = match_seeds(7, 50)
    assert seeds == match_seeds(7, 50)
    assert all(0 <= s <= 0x7FFFFFFF for s in seeds)
    assert len(set(seeds)) == 50
    assert derive_seed("a", 1) != derive_seed("a", 2)
```

`harness/tests/test_ports.py`:
```python
import socket

import pytest

from matchlab.ports import PortInUseError, PortSet, ensure_free, is_bound, port_set, wait_until_bound


def test_slots_do_not_overlap():
    assert port_set(0) == PortSet(16000, 16001, 16002)
    assert port_set(3) == PortSet(16030, 16031, 16032)


def test_port_in_use_is_reported():
    ports = port_set(40)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", ports.coach))
        with pytest.raises(PortInUseError, match=str(ports.coach)):
            ensure_free(ports)
    ensure_free(ports)


def test_bound_port_is_seen_without_binding_it():
    port = port_set(41).player
    assert not is_bound(port)
    with pytest.raises(RuntimeError, match="did not open port"):
        wait_until_bound(port, timeout_s=0.2)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", port))
        assert is_bound(port)
        wait_until_bound(port, timeout_s=1.0)
```

Run: `harness/.venv/bin/pytest harness/tests/test_seeds.py harness/tests/test_ports.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Write `harness/src/matchlab/seeds.py`**

```python
"""Deterministic seed derivation (stable across platforms and Python versions)."""

from __future__ import annotations

import hashlib


def derive_seed(*parts: object) -> int:
    digest = hashlib.sha256("/".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def match_seeds(base_seed: int, n: int) -> list[int]:
    return [derive_seed("match", base_seed, index) for index in range(n)]


def team_seed(match_seed: int, side: str) -> int:
    return derive_seed("team", match_seed, side)
```

- [ ] **Step 3: Write `harness/src/matchlab/ports.py`**

```python
"""UDP port slots for parallel matches."""

from __future__ import annotations

import socket
import subprocess
import time
from dataclasses import dataclass

BASE_PORT = 16000
STRIDE = 10


class PortInUseError(RuntimeError):
    """A port of the match slot is already in use."""


@dataclass(frozen=True)
class PortSet:
    player: int
    coach: int
    olcoach: int


def port_set(slot: int, base: int = BASE_PORT) -> PortSet:
    first = base + slot * STRIDE
    return PortSet(first, first + 1, first + 2)


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind(("", port))
        except OSError:
            return False
    return True


def ensure_free(ports: PortSet) -> None:
    for port in (ports.player, ports.coach, ports.olcoach):
        if not _free(port):
            raise PortInUseError(f"UDP port {port} is in use. Stop the other server, or use another slot.")


def is_bound(port: int) -> bool:
    """True when some process has a UDP socket on this port (Linux /proc). Does not touch the port."""
    for table in ("/proc/net/udp", "/proc/net/udp6"):
        try:
            lines = open(table).read().splitlines()[1:]
        except FileNotFoundError:
            continue
        for line in lines:
            local = line.split()[1]
            if int(local.rsplit(":", 1)[1], 16) == port:
                return True
    return False


def wait_until_bound(port: int, *, timeout_s: float = 10.0, proc: subprocess.Popen | None = None) -> None:
    # Read /proc instead of binding the port: a test bind could make the starting server fail with EADDRINUSE.
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_bound(port):
            return
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"the server exited with code {proc.returncode} before it opened port {port}")
        time.sleep(0.05)
    raise RuntimeError(f"the server did not open port {port} within {timeout_s} s")
```

- [ ] **Step 4: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_seeds.py harness/tests/test_ports.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add harness/src/matchlab/seeds.py harness/src/matchlab/ports.py harness/tests/test_seeds.py harness/tests/test_ports.py
git commit -m "feat(harness): deterministic seed derivation and UDP port slots" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Single-match runner and run records

**Covers:** tasks.md 4.4, 5.3, 5.4 (run folder and run record; log compression comes in Tasks 12 and 13: check 5.4 off in Task 13)

**Files:**
- Create: `harness/src/matchlab/record.py`, `harness/src/matchlab/match.py`, `harness/tests/conftest.py`, `harness/tests/fixtures/mini.event.csv`, `harness/tests/test_match.py`

**Interfaces:**
- Consumes: `Profile`, `SIDES` (Task 9); `team_seed` (Task 10); `PortSet`, `port_set`, `ensure_free`, `wait_until_bound` (Task 10); `Manifest`, `TeamEntry` (Task 5).
- Produces:
  - `record.py`: `RUN_SCHEMA = 1`; `write_record(run_dir: Path, data: dict) -> None`; `read_record(run_dir: Path) -> dict`; `update_record(run_dir: Path, **fields) -> dict`.
  - `match.py`: constants `PLAYERS_PER_TEAM = 11`, `CONNECT_TIMEOUT_S = 60.0`, `CONNECT_WAIT = 100_000_000`, `KICK_OFF_WAIT = 300`, `MISSED_CYCLE = "Someone missed a cycle"`, `GAVE_UP = "Waiting too long for clients! Exiting"`; `class MatchStartError(RuntimeError)`; `class MatchCancelled(Exception)`; `@dataclass(frozen=True) class MatchRecord(run_dir: Path, status: str, error: str | None, duration_s: float, missed_cycles: int)`; `server_args(profile: Profile, ports: PortSet, match_seed: int, log_dir: Path) -> list[str]`; `team_command(entry: TeamEntry, team_cfg: dict, ports: PortSet) -> list[str]`; `connected(log_text: str, team_name: str) -> tuple[int, bool]`; `wait_for_team(server_log: Path, team_cfg: dict, server: subprocess.Popen, *, timeout_s: float | None = None, cancel: threading.Event | None = None) -> None`; `run_single_match(profile: Profile, *, match_seed: int, run_dir: Path, manifest: Manifest, slot: int = 0, timeout_s: float = 3600.0, profile_hash: str | None = None, swapped: bool = False, cancel: threading.Event | None = None) -> MatchRecord`.
  - Run record (`run.json`) keys: `schema, profile_hash, swapped, match_seed, team_seeds{left,right}, teams{left,right}, pins, status (running|ok|error|timeout|cancelled|extraction-failed), error, duration_s, missed_cycles, reproducibility (not-checked|identical|differs), extraction (null|ok|failed)`.
  - Test fixture `fake_testbed` in `conftest.py` (used by Tasks 12, 13, 14, 16): a `Manifest` whose binaries are fake scripts. Environment variables: `FAKE_OUT` (folder for records), `FAKE_SERVER_MODE` (`ok`|`hang`|`fail`|`gaveup`), `FAKE_TEAM_PLAYERS` (default 11), `FAKE_MISSED` (default 0), `FAKE_RCG2DATA_MODE` (`ok`|`fail`), `FAKE_SCORE` (default `1 0`). The fake start script writes the server's connection lines to `$FAKE_OUT/connect-<port>.log`; the fake server echoes that file to its standard output (which the harness reads as `server.log`), and in mode `ok` finishes after 22 players.

- [ ] **Step 1: Write `harness/tests/conftest.py`**

```python
"""Shared test fixtures: a fake testbed made of small scripts."""

import os
import stat
from pathlib import Path

import pytest

from matchlab.manifest import Manifest, TeamEntry

FIXTURES = Path(__file__).parent / "fixtures"

FAKE_SERVER = r'''#!/usr/bin/env python3
"""Fake rcssserver: binds the player port, echoes team connections, writes logs, exits."""
import os, socket, sys, time
from pathlib import Path
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
out = Path(os.environ["FAKE_OUT"])
port = args["server::port"]
(out / f"server-args-{port}.txt").write_text("\n".join(sys.argv[1:]) + "\n")
(out / f"server-home-{port}.txt").write_text(os.environ.get("HOME", ""))
connect_log = out / f"connect-{port}.log"
connect_log.unlink(missing_ok=True)  # a new match on this port starts with no connections
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", int(port)))
mode = os.environ.get("FAKE_SERVER_MODE", "ok")
if mode == "fail":
    time.sleep(0.3)
    sys.exit(3)
seen = 0
while True:
    lines = connect_log.read_text().splitlines() if connect_log.exists() else []
    for line in lines[seen:]:
        print(line, flush=True)
    seen = len(lines)
    if mode in ("ok", "gaveup") and sum("player (" in line for line in lines) >= 22:
        break
    time.sleep(0.05)
for _ in range(int(os.environ.get("FAKE_MISSED", "0"))):
    print("Someone missed a cycle at 10", flush=True)
if mode == "gaveup":
    print("Waiting too long for clients! Exiting", flush=True)
log_dir = Path(args["server::game_log_dir"])
score = os.environ.get("FAKE_SCORE", "1 0")
(log_dir / "match.rcg").write_text(
    "ULG6\n(team 1 A B 0 0)\n(playmode 120 foul_charge_l)\n(team 600 A B " + score + ")\n")
(log_dir / "match.rcl").write_text("")
'''

FAKE_START = '''#!/bin/sh
# Fake team start script: records its input, "connects" its players, leaves one background child.
echo "$RCSC_RANDOM_SEED $*" >> "$FAKE_OUT/teams.txt"
PORT=""; NAME=""; COACH=1
while [ $# -gt 0 ]; do
  case "$1" in
    -p) PORT="$2"; shift ;;
    -t) NAME="$2"; shift ;;
    -C) COACH=0 ;;
  esac
  shift
done
i=1
while [ "$i" -le "${FAKE_TEAM_PLAYERS:-11}" ]; do
  echo "A new (v18) player ($NAME $i) connected." >> "$FAKE_OUT/connect-$PORT.log"
  i=$((i + 1))
done
if [ "$COACH" = 1 ]; then
  echo "A new (v18) online coach ($NAME) connected." >> "$FAKE_OUT/connect-$PORT.log"
fi
sleep 300 &
echo $! >> "$FAKE_OUT/children.txt"
exit 0
'''

FAKE_RCG2DATA = r'''#!/usr/bin/env python3
"""Fake rcg2data: writes the fixture events next to the input log."""
import os, shutil, sys
from pathlib import Path
if os.environ.get("FAKE_RCG2DATA_MODE", "ok") == "fail":
    sys.exit(1)
src = Path(sys.argv[1])
base = src.name.removesuffix(".gz").removesuffix(".rcg")
shutil.copy(os.environ["FAKE_EVENTS"], src.parent / f"{base}.event.csv")
'''


def _script(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def fake_testbed(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    out = tmp_path / "fakeout"
    out.mkdir()
    monkeypatch.setenv("FAKE_OUT", str(out))
    monkeypatch.setenv("FAKE_EVENTS", str(FIXTURES / "mini.event.csv"))
    start = _script(bin_dir / "start.sh", FAKE_START)
    return Manifest(
        components={"rcssserver": {"url": "fake", "ref": "fake", "patches": []}},
        rcssserver=_script(bin_dir / "rcssserver", FAKE_SERVER),
        rcssserver_lib_dirs=(),
        rcg2data=_script(bin_dir / "rcg2data", FAKE_RCG2DATA),
        rcg2data_lib_dirs=(),
        teams={"helios": TeamEntry(start, ()), "cyrus": TeamEntry(start, ())},
    )


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat_file = Path(f"/proc/{pid}/stat")
    return not (stat_file.exists() and stat_file.read_text().split()[2] == "Z")
```

Also create `harness/tests/fixtures/mini.event.csv`:
```csv
Type,Side1,Unum1,Time1,Mode1,X1,Y1,Side2,Unum2,Time2,X2,Y2,Success
Pass,left,2,10,play_on,-10,0,left,5,14,0,5,true
Pass,left,5,20,play_on,0,5,right,7,24,5,5,false
Interception,left,5,20,play_on,0,5,right,7,24,5,5,true
Dribble,right,7,25,play_on,5,5,right,7,30,10,5,true
Shoot,right,7,31,play_on,10,5,neutral,0,33,52,0,true
Tackle,left,4,40,play_on,8,5,neutral,0,40,8,5,true
Pass,right,3,50,play_on,-5,0,right,9,55,5,0,true
```

- [ ] **Step 2: Write the failing tests `harness/tests/test_match.py`**

```python
import json
import socket
import threading
import time

import pytest

import matchlab.match as match_mod
from conftest import alive
from matchlab.manifest import TeamEntry
from matchlab.match import connected, run_single_match, server_args, team_command
from matchlab.ports import PortInUseError, port_set
from matchlab.profile import load_profile
from matchlab.seeds import team_seed


def children(out):
    path = out / "children.txt"
    return [int(x) for x in path.read_text().split()] if path.exists() else []


def wait_dead(pids, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and any(alive(p) for p in pids):
        time.sleep(0.05)
    return not any(alive(p) for p in pids)


def record(run_dir):
    return json.loads((run_dir / "run.json").read_text())


def test_server_args_contain_profile_and_fixed_values(tmp_path):
    p = load_profile("short", overrides={"server": {"ball_rand": 0}})
    args = server_args(p, port_set(2), 99, tmp_path)
    assert "server::ball_rand=0" in args
    assert "server::penalty_shoot_outs=false" in args
    assert "server::half_time=30" in args and "server::nr_normal_halfs=2" in args
    assert "server::random_seed=99" in args and "server::synch_mode=true" in args
    assert "server::connect_wait=100000000" in args and "server::kick_off_wait=300" in args
    assert "server::synch_wait_clients=24" in args  # 22 players + 2 coaches
    no_coach = load_profile("short", overrides={"teams": {"right": {"coach": False}}})
    assert "server::synch_wait_clients=23" in server_args(no_coach, port_set(2), 99, tmp_path)
    assert "server::game_log_version=6" in args

    assert "server::port=16020" in args and "server::olcoach_port=16022" in args
    assert f"server::game_log_dir={tmp_path}" in args and "server::game_log_fixed_name=match" in args


def test_noise_off_reaches_the_server(tmp_path):
    args = server_args(load_profile("noise-off"), port_set(3), 1, tmp_path)
    assert "server::ball_rand=0" in args and "server::dist_noise_rate=0" in args
    assert "player::kick_rand_delta_factor=0" in args


def test_team_command(tmp_path):
    entry = TeamEntry(tmp_path / "start.sh", ())
    cmd = team_command(entry, {"team": "helios", "name": "HELIOS_L", "coach": False}, port_set(1))
    assert cmd == [str(tmp_path / "start.sh"), "-h", "127.0.0.1", "-p", "16010", "-P", "16012", "-t", "HELIOS_L", "-C"]


def test_connected_counts_players_and_coach():
    log = ("A new (v18) player (HELIOS_L 1) connected.\nA new (v18) player (HELIOS_L 2) connected.\n"
           "A new (v18) player (HELIOS_R 1) connected.\nA new (v18) online coach (HELIOS_L) connected.\n")
    assert connected(log, "HELIOS_L") == (2, True)
    assert connected(log, "HELIOS_R") == (1, False)


def test_ok_match_writes_run_folder_and_kills_children(fake_testbed, tmp_path):
    out = tmp_path / "fakeout"
    run_dir = tmp_path / "run"
    rec = run_single_match(load_profile("short"), match_seed=737161366, run_dir=run_dir,
                           manifest=fake_testbed, slot=11, timeout_s=30)
    assert rec.status == "ok", rec.error
    data = record(run_dir)
    assert data["status"] == "ok" and data["reproducibility"] == "not-checked" and data["missed_cycles"] == 0
    assert data["team_seeds"] == {"left": 1608858898, "right": 308656577}
    assert data["profile_hash"] == load_profile("short").hash
    assert json.loads((run_dir / "profile.json").read_text()) == load_profile("short").data
    assert (run_dir / "match.rcg").is_file()
    lines = (out / "teams.txt").read_text().splitlines()
    assert lines[0].startswith(f"{team_seed(737161366, 'left')} ") and "-t HELIOS_L" in lines[0]
    assert lines[1].startswith(f"{team_seed(737161366, 'right')} ") and "-t HELIOS_R" in lines[1]
    assert (out / f"server-home-{port_set(11).player}.txt").read_text() == str(run_dir / "home")
    assert wait_dead(children(out))


def test_missed_cycles_are_counted(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MISSED", "2")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=16, timeout_s=30)
    assert rec.status == "ok" and rec.missed_cycles == 2
    assert record(tmp_path / "run")["missed_cycles"] == 2


def test_server_that_gave_up_is_an_error(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "gaveup")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=19, timeout_s=30)
    assert rec.status == "error" and "gave up waiting for clients" in rec.error


def test_team_that_does_not_connect_is_an_error(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_TEAM_PLAYERS", "9")
    monkeypatch.setattr(match_mod, "CONNECT_TIMEOUT_S", 0.5)
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=17, timeout_s=30)
    assert rec.status == "error" and "HELIOS_L connected 9 of 11 players" in rec.error
    assert len((tmp_path / "fakeout" / "teams.txt").read_text().splitlines()) == 1  # right team never started
    assert wait_dead(children(tmp_path / "fakeout"))


def test_timeout_kills_everything(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "hang")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=12, timeout_s=1)
    assert rec.status == "timeout"
    assert record(tmp_path / "run")["status"] == "timeout"
    assert wait_dead(children(tmp_path / "fakeout"))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", port_set(12).player))  # the fake server released its port


def test_server_failure_is_error(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "fail")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=13, timeout_s=30)
    assert rec.status == "error" and "exit code 3" in rec.error


def test_port_in_use_starts_nothing(fake_testbed, tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", port_set(14).player))
        with pytest.raises(PortInUseError):
            run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                             manifest=fake_testbed, slot=14, timeout_s=30)
    assert not list((tmp_path / "fakeout").glob("server-args-*"))


def test_cancel_stops_match(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "hang")
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    started = time.monotonic()
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=18, timeout_s=60, cancel=cancel)
    assert rec.status == "cancelled" and time.monotonic() - started < 15
    assert wait_dead(children(tmp_path / "fakeout"))


def test_interrupt_kills_processes(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "hang")

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt  # as if the user pressed Ctrl-C after the left team started

    monkeypatch.setattr(match_mod, "wait_for_team", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                         manifest=fake_testbed, slot=15, timeout_s=30)
    assert wait_dead(children(tmp_path / "fakeout"))
    assert record(tmp_path / "run")["status"] == "cancelled"
```

Run: `harness/.venv/bin/pytest harness/tests/test_match.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `harness/src/matchlab/record.py`**

```python
"""Read and write run.json, the record of one match."""

from __future__ import annotations

import json
from pathlib import Path

RUN_SCHEMA = 1


def write_record(run_dir: Path, data: dict) -> None:
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(run_dir / "run.json")


def read_record(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text())


def update_record(run_dir: Path, **fields) -> dict:
    data = read_record(run_dir)
    data.update(fields)
    write_record(run_dir, data)
    return data
```

- [ ] **Step 4: Write `harness/src/matchlab/match.py`**

```python
"""Run one match: server and two teams in one process group, one run folder."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, TeamEntry
from .ports import PortSet, ensure_free, port_set, wait_until_bound
from .profile import SIDES, Profile
from .record import RUN_SCHEMA, write_record
from .seeds import team_seed

PLAYERS_PER_TEAM = 11
CONNECT_TIMEOUT_S = 60.0
# In synch mode, cycles before all 22 players connect take microseconds. The default
# connect_wait (300 cycles) would end at once and auto mode would kick off an empty match.
CONNECT_WAIT = 100_000_000
# Cycles between the 22nd player and kick-off: time for the last coach to connect.
KICK_OFF_WAIT = 300
MISSED_CYCLE = "Someone missed a cycle"
GAVE_UP = "Waiting too long for clients! Exiting"

_PLAYER = re.compile(r"player \((\S+) (\d+)\) connected\.")
_COACH = re.compile(r"online coach \((\S+)\) connected\.")


class MatchStartError(RuntimeError):
    """A team did not connect, or the server ended before the match started."""


class MatchCancelled(Exception):
    """The caller asked to stop the match."""


@dataclass(frozen=True)
class MatchRecord:
    run_dir: Path
    status: str
    error: str | None
    duration_s: float
    missed_cycles: int


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def server_args(profile: Profile, ports: PortSet, match_seed: int, log_dir: Path) -> list[str]:
    fixed = {
        "port": ports.player, "coach_port": ports.coach, "olcoach_port": ports.olcoach,
        "synch_mode": True, "auto_mode": True, "random_seed": match_seed,
        "connect_wait": CONNECT_WAIT, "kick_off_wait": KICK_OFF_WAIT,
        # rcssserver patch 0003: no step before all players and enabled coaches are connected
        "synch_wait_clients": 2 * PLAYERS_PER_TEAM + sum(1 for side in SIDES if profile.team(side)["coach"]),
        "game_logging": True, "text_logging": True,
        "game_log_dir": log_dir, "text_log_dir": log_dir,
        "game_log_fixed": True, "text_log_fixed": True,
        "game_log_fixed_name": "match", "text_log_fixed_name": "match",
        "game_log_compression": 0, "text_log_compression": 0, "game_log_version": 6,  # ULG6 text format
        "nr_normal_halfs": profile.data["match"]["halves"], "half_time": profile.data["match"]["half_time"],
    }
    args = [f"server::{k}={_fmt(v)}" for k, v in sorted(profile.data["server"].items())]
    args += [f"player::{k}={_fmt(v)}" for k, v in sorted(profile.data["player"].items())]
    args += [f"server::{k}={_fmt(v)}" for k, v in sorted(fixed.items())]
    return args


def team_command(entry: TeamEntry, team_cfg: dict, ports: PortSet) -> list[str]:
    cmd = [str(entry.start), "-h", "127.0.0.1", "-p", str(ports.player), "-P", str(ports.olcoach),
           "-t", team_cfg["name"]]
    if not team_cfg["coach"]:
        cmd.append("-C")
    return cmd


def connected(log_text: str, team_name: str) -> tuple[int, bool]:
    players = {m.group(2) for m in _PLAYER.finditer(log_text) if m.group(1) == team_name}
    coach = any(m.group(1) == team_name for m in _COACH.finditer(log_text))
    return len(players), coach


def wait_for_team(server_log: Path, team_cfg: dict, server: subprocess.Popen, *,
                  timeout_s: float | None = None, cancel: threading.Event | None = None) -> None:
    name = team_cfg["name"]
    timeout_s = CONNECT_TIMEOUT_S if timeout_s is None else timeout_s
    deadline = time.monotonic() + timeout_s
    while True:
        players, coach = connected(server_log.read_text(errors="replace"), name)
        if players >= PLAYERS_PER_TEAM and (coach or not team_cfg["coach"]):
            return
        if server.poll() is not None:
            raise MatchStartError(f"the server ended with exit code {server.returncode} before team {name} connected")
        if cancel is not None and cancel.is_set():
            raise MatchCancelled()
        if time.monotonic() > deadline:
            no_coach = "" if coach or not team_cfg["coach"] else " and no coach"
            raise MatchStartError(
                f"team {name} connected {players} of {PLAYERS_PER_TEAM} players{no_coach} within {timeout_s} s")
        time.sleep(0.05)


def _wait_server(server: subprocess.Popen, timeout_s: float, cancel: threading.Event | None) -> int | None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return server.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                raise MatchCancelled() from None
            if time.monotonic() > deadline:
                return None


def _env(lib_dirs, **extra: str) -> dict[str, str]:
    env = os.environ.copy()
    if lib_dirs:
        parts = [str(p) for p in lib_dirs] + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else [])
        env["LD_LIBRARY_PATH"] = ":".join(parts)
    env.update(extra)
    return env


def _tail(path: Path, lines: int = 5) -> str:
    if not path.exists():
        return ""
    return " | ".join(path.read_text(errors="replace").strip().splitlines()[-lines:])


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _kill_group(pgid: int, server: subprocess.Popen | None) -> None:
    for sig, wait_s in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if server is not None:
                server.poll()
            if not _group_alive(pgid):
                break
            time.sleep(0.05)
        if not _group_alive(pgid):
            break
    if server is not None:
        try:
            server.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def run_single_match(profile: Profile, *, match_seed: int, run_dir: Path, manifest: Manifest, slot: int = 0,
                     timeout_s: float = 3600.0, profile_hash: str | None = None, swapped: bool = False,
                     cancel: threading.Event | None = None) -> MatchRecord:
    ports = port_set(slot)
    ensure_free(ports)
    run_dir.mkdir(parents=True, exist_ok=False)
    home = run_dir / "home"
    home.mkdir()
    seeds = {side: team_seed(match_seed, side) for side in SIDES}
    (run_dir / "profile.json").write_text(json.dumps(profile.data, indent=2, sort_keys=True) + "\n")
    record = {
        "schema": RUN_SCHEMA,
        "profile_hash": profile_hash or profile.hash,
        "played_profile_hash": profile.hash,  # differs from profile_hash in swapped matches
        "swapped": swapped,
        "match_seed": match_seed,
        "team_seeds": seeds,
        "teams": {side: profile.team(side) for side in SIDES},
        "pins": manifest.pins(),
        "status": "running",
        "error": None,
        "duration_s": None,
        "missed_cycles": None,
        "reproducibility": "not-checked",
        "extraction": None,
    }
    write_record(run_dir, record)

    server_log_path = run_dir / "server.log"
    status, error = "error", None
    server: subprocess.Popen | None = None
    logs = []
    start = time.monotonic()
    try:
        server_log = server_log_path.open("wb")
        logs.append(server_log)
        server = subprocess.Popen(
            [str(manifest.rcssserver), *server_args(profile, ports, match_seed, run_dir)],
            cwd=run_dir, env=_env(manifest.rcssserver_lib_dirs, HOME=str(home)),
            stdout=server_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, process_group=0,
        )
        try:
            wait_until_bound(ports.player, proc=server)
        except RuntimeError as exc:
            raise MatchStartError(str(exc)) from exc
        for side in SIDES:
            team_cfg = profile.team(side)
            entry = manifest.teams[team_cfg["team"]]
            team_log = (run_dir / f"team-{side}.log").open("wb")
            logs.append(team_log)
            try:
                starter = subprocess.Popen(
                    team_command(entry, team_cfg, ports), cwd=entry.start.parent,
                    env=_env(entry.lib_dirs, RCSC_RANDOM_SEED=str(seeds[side])),
                    stdout=team_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, process_group=server.pid,
                )
            except OSError as exc:  # the server's process group is gone when the server already ended
                if server.poll() is not None:
                    raise MatchStartError(
                        f"the server ended with exit code {server.returncode} before the {side} team started") from exc
                raise MatchStartError(f"cannot start the {side} team: {exc}") from exc
            try:
                starter_code = starter.wait(timeout=60)
            except subprocess.TimeoutExpired as exc:
                raise MatchStartError(f"the {side} team start script did not exit within 60 s") from exc
            if starter_code != 0:
                raise MatchStartError(f"the {side} team start script exited with code {starter_code}")
            wait_for_team(server_log_path, team_cfg, server, cancel=cancel)
        code = _wait_server(server, timeout_s, cancel)
        if code is None:
            status, error = "timeout", f"the match did not end within {timeout_s} s"
        elif code == 0 and (run_dir / "match.rcg").is_file():
            status = "ok"
        else:
            error = f"the server ended with exit code {code}" + (
                "" if (run_dir / "match.rcg").is_file() else " and wrote no match.rcg")
    except MatchCancelled:
        status, error = "cancelled", "the match was cancelled"
    except MatchStartError as exc:
        error = str(exc)
    except KeyboardInterrupt:
        status, error = "cancelled", "the match was interrupted (Ctrl-C)"
        raise
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if server is not None:
            _kill_group(server.pid, server)
        for fh in logs:
            fh.close()
        log_text = server_log_path.read_text(errors="replace") if server_log_path.exists() else ""
        missed = log_text.count(MISSED_CYCLE)
        if status == "ok" and GAVE_UP in log_text:
            status, error = "error", "the server gave up waiting for clients"
        if status in ("error", "timeout") and error:
            error = f"{error}; server.log ends with: {_tail(server_log_path)}"
        duration = round(time.monotonic() - start, 3)
        record.update(status=status, error=error, duration_s=duration, missed_cycles=missed)
        write_record(run_dir, record)
    return MatchRecord(run_dir, status, error, duration, missed)
```

- [ ] **Step 5: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_match.py -q`
Expected: `13 passed`.

- [ ] **Step 6: Commit**

```bash
git add harness/src/matchlab/record.py harness/src/matchlab/match.py harness/tests/conftest.py harness/tests/test_match.py harness/tests/fixtures
git commit -m "feat(harness): run one seeded match with ordered team connection and cancellation" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Game log parsing and the reproducibility check

**Covers:** tasks.md 5.6; the game log part of 6.2 (check 6.2 off in Task 13)

**Files:**
- Create: `harness/src/matchlab/rcg.py`, `harness/src/matchlab/repro.py`, `harness/tests/fixtures/mini.rcg`, `harness/tests/test_rcg.py`, `harness/tests/test_repro.py`

**Interfaces:**
- Consumes: `run_single_match`, `MatchRecord` (Task 11); `update_record` (Task 11); `Profile`; `Manifest`.
- Produces:
  - `rcg.py`: `class RcgError(ValueError)`; `@dataclass(frozen=True) class FinalScore(left_name: str, right_name: str, left: int, right: int)`; `open_binary(path: Path)` (handles `.gz`); `final_score(path: Path) -> FinalScore`; `foul_counts(path: Path) -> dict[str, int]` (keys `left`, `right`); `show_cycle(line: bytes) -> int | None`; `game_log(run_dir: Path) -> Path` (`match.rcg`, else `match.rcg.gz`); `compress_logs(run_dir: Path) -> None` (gzips `match.rcg` and `match.rcl`, removes originals).
  - `repro.py`: `SKIP_PREFIXES: tuple[bytes, ...]` (value from the Task 8 decision; `()` if none); `@dataclass(frozen=True) class ReproResult(status: str, first_difference: dict | None, skipped: tuple[str, ...])`; `compare_rcg(a: Path, b: Path, skip_prefixes: tuple[bytes, ...] = SKIP_PREFIXES) -> ReproResult`; `replay_and_compare(profile: Profile, match_seed: int, original_run_dir: Path, replay_dir: Path, manifest: Manifest, *, slot: int = 0, timeout_s: float = 3600.0, profile_hash: str | None = None) -> ReproResult` (raises `RuntimeError` if the replay does not finish; sets `reproducibility` in both run records; compresses both logs); `check_reproducibility(profile: Profile, match_seed: int, out_dir: Path, manifest: Manifest, *, slot: int = 0, timeout_s: float = 3600.0) -> ReproResult` (runs `a`, replays as `b`, writes `out_dir/repro.json`).

- [ ] **Step 1: Write the fixture `harness/tests/fixtures/mini.rcg`**

```text
ULG6
(server_param (half_time 30))
(team 1 HELIOS_L HELIOS_R 0 0)
(playmode 1 kick_off_l)
(show 1 ((b) 0 0 0 0))
(playmode 120 foul_charge_l)
(playmode 121 free_kick_r)
(show 200 ((b) 0 0 0 0))
(playmode 300 goal_l)
(team 300 HELIOS_L HELIOS_R 1 0)
(playmode 450 foul_push_r)
(show 450 ((b) 0 0 0 0))
(team 600 HELIOS_L HELIOS_R 2 1)
(playmode 600 time_over)
```

- [ ] **Step 2: Write the failing tests**

`harness/tests/test_rcg.py`:
```python
import gzip
import shutil
from pathlib import Path

import pytest

from matchlab.rcg import FinalScore, RcgError, compress_logs, final_score, foul_counts, game_log, show_cycle

MINI = Path(__file__).parent / "fixtures" / "mini.rcg"


def test_final_score_and_fouls():
    assert final_score(MINI) == FinalScore("HELIOS_L", "HELIOS_R", 2, 1)
    assert foul_counts(MINI) == {"left": 1, "right": 1}


def test_gzip_is_read(tmp_path):
    gz = tmp_path / "m.rcg.gz"
    with gzip.open(gz, "wb") as fh:
        fh.write(MINI.read_bytes())
    assert final_score(gz).left == 2


def test_no_team_line(tmp_path):
    bad = tmp_path / "bad.rcg"
    bad.write_text("ULG6\n(show 1 ((b) 0 0 0 0))\n")
    with pytest.raises(RcgError, match="no final score"):
        final_score(bad)


def test_show_cycle():
    assert show_cycle(b"(show 42 ((b) 0 0 0 0))\n") == 42
    assert show_cycle(b"(team 1 A B 0 0)\n") is None


def test_compress_logs_and_game_log(tmp_path):
    shutil.copy(MINI, tmp_path / "match.rcg")
    (tmp_path / "match.rcl").write_text("x\n")
    assert game_log(tmp_path) == tmp_path / "match.rcg"
    compress_logs(tmp_path)
    assert not (tmp_path / "match.rcg").exists()
    assert gzip.open(tmp_path / "match.rcg.gz").read() == MINI.read_bytes()
    assert (tmp_path / "match.rcl.gz").exists()
    assert game_log(tmp_path) == tmp_path / "match.rcg.gz"
```

`harness/tests/test_repro.py`:
```python
import json

from matchlab.profile import load_profile
from matchlab.repro import check_reproducibility, compare_rcg

A = b"ULG6\n(show 1 x)\n(show 2 x)\n(show 3 a)\n"


def test_identical(tmp_path):
    (tmp_path / "a").write_bytes(A)
    (tmp_path / "b").write_bytes(A)
    assert compare_rcg(tmp_path / "a", tmp_path / "b").status == "identical"


def test_first_difference_has_line_and_cycle(tmp_path):
    (tmp_path / "a").write_bytes(A)
    (tmp_path / "b").write_bytes(A.replace(b"(show 3 a)", b"(show 3 b)"))
    result = compare_rcg(tmp_path / "a", tmp_path / "b")
    assert result.status == "differs"
    assert result.first_difference["line"] == 4 and result.first_difference["cycle"] == 3


def test_shorter_file_differs(tmp_path):
    (tmp_path / "a").write_bytes(A)
    (tmp_path / "b").write_bytes(A[:-11])
    assert compare_rcg(tmp_path / "a", tmp_path / "b").first_difference["b"] == "<end of file>"


def test_skipped_prefix_is_listed(tmp_path):
    (tmp_path / "a").write_bytes(b"(stamp 1)\n" + A)
    (tmp_path / "b").write_bytes(b"(stamp 2)\n" + A)
    result = compare_rcg(tmp_path / "a", tmp_path / "b", skip_prefixes=(b"(stamp ",))
    assert result.status == "identical" and result.skipped == ("(stamp ",)


def test_check_with_fake_testbed(fake_testbed, tmp_path):
    result = check_reproducibility(load_profile("short"), 5, tmp_path / "repro", fake_testbed, slot=21, timeout_s=30)
    assert result.status == "identical"
    saved = json.loads((tmp_path / "repro" / "repro.json").read_text())
    assert saved["status"] == "identical"
    for run in ("a", "b"):
        record = json.loads((tmp_path / "repro" / run / "run.json").read_text())
        assert record["reproducibility"] == "identical"
        assert (tmp_path / "repro" / run / "match.rcg.gz").exists()
```

Run: `harness/.venv/bin/pytest harness/tests/test_rcg.py harness/tests/test_repro.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `harness/src/matchlab/rcg.py`**

```python
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
```

- [ ] **Step 4: Write `harness/src/matchlab/repro.py`**

`SKIP_PREFIXES` holds the two prefixes recorded in design.md D5 after Task 8: `(server_param` (per-run log folder paths) and `(msg ` (result line with a time stamp). They hold no play data; skipping them makes the reported first difference point at the real divergence.

```python
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


@dataclass(frozen=True)
class ReproResult:
    status: str
    first_difference: dict | None
    skipped: tuple[str, ...]


def _text(line: bytes | None) -> str:
    return "<end of file>" if line is None else line.rstrip(b"\n").decode(errors="replace")[:200]


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
            return ReproResult("differs", {"line": number, "cycle": cycle, "a": _text(la), "b": _text(lb)},
                               skipped)
    return ReproResult("identical", None, skipped)


def replay_and_compare(profile: Profile, match_seed: int, original_run_dir: Path, replay_dir: Path,
                       manifest: Manifest, *, slot: int = 0, timeout_s: float = 3600.0,
                       profile_hash: str | None = None) -> ReproResult:
    rec = run_single_match(profile, match_seed=match_seed, run_dir=replay_dir, manifest=manifest, slot=slot,
                           timeout_s=timeout_s, profile_hash=profile_hash)
    if rec.status != "ok":
        raise RuntimeError(f"the replay did not finish ({rec.status}: {rec.error}); see {replay_dir}")
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
        raise RuntimeError(f"run a did not finish ({first.status}: {first.error}); see {first.run_dir}")
    result = replay_and_compare(profile, match_seed, out_dir / "a", out_dir / "b", manifest,
                                slot=slot, timeout_s=timeout_s)
    (out_dir / "repro.json").write_text(json.dumps(
        {"profile_hash": profile.hash, "match_seed": match_seed, **asdict(result)}, indent=2, sort_keys=True) + "\n")
    return result
```

- [ ] **Step 5: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_rcg.py harness/tests/test_repro.py -q`
Expected: `10 passed`.

- [ ] **Step 6: Commit**

```bash
git add harness/src/matchlab/rcg.py harness/src/matchlab/repro.py harness/tests/test_rcg.py harness/tests/test_repro.py harness/tests/fixtures/mini.rcg
git commit -m "feat(harness): read game logs and replay matches to check reproducibility" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Event extraction and per-match metrics

**Covers:** tasks.md 6.1, 6.2, 6.3, and 5.4 (log compression is now complete)

**Files:**
- Create: `harness/src/matchlab/metrics.py`, `harness/tests/test_metrics.py`

**Interfaces:**
- Consumes: `final_score`, `foul_counts`, `compress_logs`, `FinalScore`, `RcgError` (Task 12); `update_record` (Task 11); `Manifest` (Task 5); fixtures `mini.rcg`, `mini.event.csv`, `fake_testbed`.
- Produces: `EVENTS_COLUMNS: list[str]`; `METRICS_SCHEMA = 1`; `read_events(path: Path) -> list[dict[str, str]]`; `compute_metrics(score: FinalScore, fouls: dict[str, int], events: list[dict[str, str]]) -> dict`; `extract_and_measure(run_dir: Path, manifest: Manifest) -> dict | None`.
- Metrics JSON shape: `{"schema": 1, "sides": {"left": {...}, "right": {...}}}`, each side with keys `team, goals, goal_difference, shots, passes, pass_completion, interceptions, tackles, fouls, event_possession_share`.

- [ ] **Step 1: Write the failing tests `harness/tests/test_metrics.py`**

```python
import json
import shutil
from pathlib import Path

import pytest

from matchlab.metrics import compute_metrics, extract_and_measure, read_events
from matchlab.rcg import final_score, foul_counts
from matchlab.record import write_record

FIX = Path(__file__).parent / "fixtures"


def test_metrics_from_known_log():
    m = compute_metrics(final_score(FIX / "mini.rcg"), foul_counts(FIX / "mini.rcg"),
                        read_events(FIX / "mini.event.csv"))
    left, right = m["sides"]["left"], m["sides"]["right"]
    assert m["schema"] == 1
    assert (left["goals"], right["goals"]) == (2, 1)
    assert (left["goal_difference"], right["goal_difference"]) == (1, -1)
    assert (left["passes"], left["pass_completion"]) == (2, 0.5)
    assert (right["passes"], right["pass_completion"]) == (1, 1.0)
    assert (left["interceptions"], right["interceptions"]) == (0, 1)
    assert (left["shots"], right["shots"]) == (0, 1)
    assert (left["tackles"], right["tackles"]) == (1, 0)
    assert (left["fouls"], right["fouls"]) == (1, 1)
    assert left["event_possession_share"] == pytest.approx(0.4)
    assert left["event_possession_share"] + right["event_possession_share"] == pytest.approx(1.0)
    assert left["team"] == "HELIOS_L"


def test_no_passes_gives_null(tmp_path):
    csv = tmp_path / "e.csv"
    csv.write_text((FIX / "mini.event.csv").read_text().splitlines()[0] + "\n")
    m = compute_metrics(final_score(FIX / "mini.rcg"), {"left": 0, "right": 0}, read_events(csv))
    assert m["sides"]["left"]["pass_completion"] is None
    assert m["sides"]["left"]["event_possession_share"] is None


def test_wrong_header_is_rejected(tmp_path):
    csv = tmp_path / "e.csv"
    csv.write_text("A,B\n1,2\n")
    with pytest.raises(ValueError, match="unexpected events CSV header"):
        read_events(csv)


def run_dir_with_log(tmp_path, rcg_text=None):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    if rcg_text is None:
        shutil.copy(FIX / "mini.rcg", run_dir / "match.rcg")
    else:
        (run_dir / "match.rcg").write_text(rcg_text)
    (run_dir / "match.rcl").write_text("")
    write_record(run_dir, {"status": "ok", "extraction": None, "error": None})
    return run_dir


def test_extract_and_measure(fake_testbed, tmp_path):
    run_dir = run_dir_with_log(tmp_path)
    metrics = extract_and_measure(run_dir, fake_testbed)
    assert metrics["sides"]["left"]["goals"] == 2
    assert json.loads((run_dir / "metrics.json").read_text()) == metrics
    assert (run_dir / "events.csv").is_file() and not (run_dir / "match.event.csv").exists()
    assert (run_dir / "match.rcg.gz").is_file() and not (run_dir / "match.rcg").exists()
    assert json.loads((run_dir / "run.json").read_text())["extraction"] == "ok"


def test_extraction_failure(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_RCG2DATA_MODE", "fail")
    run_dir = run_dir_with_log(tmp_path)
    assert extract_and_measure(run_dir, fake_testbed) is None
    record = json.loads((run_dir / "run.json").read_text())
    assert record["status"] == "extraction-failed" and record["extraction"] == "failed"
    assert not (run_dir / "metrics.json").exists()


def test_log_without_score_is_extraction_failure(fake_testbed, tmp_path):
    run_dir = run_dir_with_log(tmp_path, "ULG6\n(show 1 ((b) 0 0 0 0))\n")
    assert extract_and_measure(run_dir, fake_testbed) is None
    record = json.loads((run_dir / "run.json").read_text())
    assert record["status"] == "extraction-failed" and "no final score" in record["error"]
```

Run: `harness/.venv/bin/pytest harness/tests/test_metrics.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Write `harness/src/matchlab/metrics.py`**

```python
"""SPADL events from rcg2data, and per-match metrics."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from .manifest import Manifest
from .rcg import FinalScore, RcgError, compress_logs, final_score, foul_counts
from .record import update_record

EVENTS_COLUMNS = ["Type", "Side1", "Unum1", "Time1", "Mode1", "X1", "Y1",
                  "Side2", "Unum2", "Time2", "X2", "Y2", "Success"]
METRICS_SCHEMA = 1
SIDES = ("left", "right")
POSSESSION_TYPES = frozenset({"Pass", "Dribble", "Shoot"})


def read_events(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != EVENTS_COLUMNS:
            raise ValueError(f"{Path(path).name}: unexpected events CSV header {reader.fieldnames}")
        return list(reader)


def compute_metrics(score: FinalScore, fouls: dict[str, int], events: list[dict[str, str]]) -> dict:
    count = {name: Counter() for name in ("shots", "passes", "passes_ok", "interceptions", "tackles", "possession")}
    for event in events:
        kind, side1, side2 = event["Type"], event["Side1"], event["Side2"]
        if kind == "Pass" and side1 in SIDES:
            count["passes"][side1] += 1
            if event["Success"] == "true":
                count["passes_ok"][side1] += 1
        elif kind == "Shoot" and side1 in SIDES:
            count["shots"][side1] += 1
        elif kind == "Tackle" and side1 in SIDES:
            count["tackles"][side1] += 1
        elif kind == "Interception" and side2 in SIDES:
            count["interceptions"][side2] += 1
        if kind in POSSESSION_TYPES and side1 in SIDES:
            count["possession"][side1] += 1
    goals = {"left": score.left, "right": score.right}
    names = {"left": score.left_name, "right": score.right_name}
    total_possession = sum(count["possession"].values())
    sides = {}
    for side in SIDES:
        other = "right" if side == "left" else "left"
        passes = count["passes"][side]
        sides[side] = {
            "team": names[side],
            "goals": goals[side],
            "goal_difference": goals[side] - goals[other],
            "shots": count["shots"][side],
            "passes": passes,
            "pass_completion": count["passes_ok"][side] / passes if passes else None,
            "interceptions": count["interceptions"][side],
            "tackles": count["tackles"][side],
            "fouls": fouls.get(side, 0),
            "event_possession_share": (count["possession"][side] / total_possession
                                       if total_possession else None),
        }
    return {"schema": METRICS_SCHEMA, "sides": sides}


def _env(manifest: Manifest) -> dict[str, str]:
    env = os.environ.copy()
    dirs = [str(p) for p in manifest.rcg2data_lib_dirs]
    if dirs:
        env["LD_LIBRARY_PATH"] = ":".join(dirs + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    return env


def extract_and_measure(run_dir: Path, manifest: Manifest) -> dict | None:
    rcg = run_dir / "match.rcg"
    try:
        result = subprocess.run([str(manifest.rcg2data), str(rcg)], cwd=run_dir, env=_env(manifest),
                                capture_output=True, text=True, timeout=600)
        produced = run_dir / "match.event.csv"
        if result.returncode != 0 or not produced.is_file():
            raise RuntimeError(f"rcg2data exit code {result.returncode}: {result.stderr.strip()[-500:]}")
        events_path = run_dir / "events.csv"
        produced.replace(events_path)
        metrics = compute_metrics(final_score(rcg), foul_counts(rcg), read_events(events_path))
    except (RuntimeError, RcgError, ValueError, subprocess.TimeoutExpired) as exc:
        update_record(run_dir, status="extraction-failed", extraction="failed", error=str(exc))
        compress_logs(run_dir)
        return None
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    update_record(run_dir, extraction="ok")
    compress_logs(run_dir)
    return metrics
```

- [ ] **Step 3: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_metrics.py -q`
Expected: `6 passed`.

- [ ] **Step 4: Commit**

```bash
git add harness/src/matchlab/metrics.py harness/tests/test_metrics.py
git commit -m "feat(harness): extract SPADL events with rcg2data and compute per-match metrics" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Batch runner (`run_matches`)

**Covers:** tasks.md 5.5

**Files:**
- Create: `harness/src/matchlab/runner.py`, `harness/tests/test_runner.py`

**Interfaces:**
- Consumes: `run_single_match` (Task 11); `extract_and_measure` (Task 13); `read_record` (Task 11); `load_manifest` (Task 5); `Profile` (Task 9).
- Produces: `@dataclass(frozen=True) class MatchResult(index: int, swapped: bool, match_seed: int, run_dir: Path, status: str, metrics: dict | None, reproducibility: str, missed_cycles: int)`; `run_matches(profile: Profile, seeds: Sequence[int], *, out_dir: Path, manifest: Manifest | None = None, workers: int = 1, timeout_s: float = 3600.0, swap_sides: bool = False, cancel: threading.Event | None = None) -> list[MatchResult]`. Run folders: `out_dir/NNNN-normal` and `out_dir/NNNN-swapped`. Results are in job order: all normal matches, then all swapped matches. A match that has not started when the cancel flag is set gets status `cancelled` and no run folder. Before any process starts, `run_matches` raises `ProfileError` if a profile team is not in the manifest. Ctrl-C (`KeyboardInterrupt`) sets the cancel flag, waits until every running match has stopped its processes, then re-raises.

- [ ] **Step 1: Write the failing tests `harness/tests/test_runner.py`**

```python
import threading
import time

import pytest

from conftest import alive
from matchlab.profile import load_profile
from matchlab.runner import run_matches


def test_runs_all_seeds_in_parallel_slots(fake_testbed, tmp_path):
    results = run_matches(load_profile("short"), [11, 22, 33], out_dir=tmp_path / "out",
                          manifest=fake_testbed, workers=2, timeout_s=30)
    assert [r.match_seed for r in results] == [11, 22, 33]
    assert all(r.status == "ok" for r in results)
    assert all(r.metrics["sides"]["left"]["goals"] == 1 for r in results)
    assert [r.run_dir.name for r in results] == ["0000-normal", "0001-normal", "0002-normal"]
    assert all(r.reproducibility == "not-checked" and r.missed_cycles == 0 for r in results)
    used = {p.name for p in (tmp_path / "fakeout").glob("server-args-*.txt")}
    assert used == {"server-args-16000.txt", "server-args-16010.txt"}  # two slots, two port sets


def test_swap_sides_adds_swapped_runs(fake_testbed, tmp_path):
    results = run_matches(load_profile("short"), [5], out_dir=tmp_path / "out", manifest=fake_testbed,
                          timeout_s=30, swap_sides=True)
    assert [(r.index, r.swapped) for r in results] == [(0, False), (0, True)]
    assert (tmp_path / "out" / "0000-swapped" / "run.json").is_file()


def test_failed_match_has_no_metrics(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "fail")
    [result] = run_matches(load_profile("short"), [1], out_dir=tmp_path / "out", manifest=fake_testbed, timeout_s=30)
    assert result.status == "error" and result.metrics is None


def test_cancel_stops_batch(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "hang")
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    started = time.monotonic()
    results = run_matches(load_profile("short"), [1, 2], out_dir=tmp_path / "out", manifest=fake_testbed,
                          timeout_s=60, cancel=cancel)
    assert [r.status for r in results] == ["cancelled", "cancelled"]
    assert time.monotonic() - started < 20
    children = [int(x) for x in (tmp_path / "fakeout" / "children.txt").read_text().split()]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(alive(p) for p in children):
        time.sleep(0.05)
    assert not any(alive(p) for p in children)


def test_unknown_team_is_rejected_before_any_process(fake_testbed, tmp_path):
    from matchlab.profile import ProfileError
    profile = load_profile("short", overrides={"teams": {"right": {"team": "nobody"}}})
    with pytest.raises(ProfileError, match="unknown team 'nobody'"):
        run_matches(profile, [1], out_dir=tmp_path / "out", manifest=fake_testbed)
    assert not (tmp_path / "fakeout" / "teams.txt").exists()


def test_existing_run_folder_is_refused(fake_testbed, tmp_path):
    (tmp_path / "out" / "0000-normal").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        run_matches(load_profile("short"), [1], out_dir=tmp_path / "out", manifest=fake_testbed, timeout_s=30)


def test_workers_must_be_positive(fake_testbed, tmp_path):
    with pytest.raises(ValueError, match="workers"):
        run_matches(load_profile("short"), [1], out_dir=tmp_path, manifest=fake_testbed, workers=0)
```

Run: `harness/.venv/bin/pytest harness/tests/test_runner.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Write `harness/src/matchlab/runner.py`**

```python
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
```

- [ ] **Step 3: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_runner.py -q`
Expected: `7 passed`.

- [ ] **Step 4: Commit**

```bash
git add harness/src/matchlab/runner.py harness/tests/test_runner.py
git commit -m "feat(harness): run batches of matches with port slots and cancellation" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Statistics

**Covers:** tasks.md 7.3

**Files:**
- Create: `harness/src/matchlab/stats.py`, `harness/tests/test_stats.py`

**Interfaces:**
- Produces: `Z95 = 1.959963984540054`; `BOOTSTRAP_RESAMPLES = 10_000`; `BOOTSTRAP_SEED = 20261011`; `mean(values: Sequence[float]) -> float | None`; `wilson_interval(k: int, n: int, z: float = Z95) -> list[float] | None`; `bootstrap_mean_ci(values: Sequence[float], *, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED, level: float = 0.95) -> list[float] | None`. Intervals are 2-item lists (JSON-friendly).

- [ ] **Step 1: Write the failing tests `harness/tests/test_stats.py`**

```python
import pytest

from matchlab.stats import bootstrap_mean_ci, mean, wilson_interval


def test_wilson_known_values():
    lo, hi = wilson_interval(7, 10)
    assert lo == pytest.approx(0.396778, abs=1e-6)
    assert hi == pytest.approx(0.892209, abs=1e-6)
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == 1.0
    assert wilson_interval(0, 7)[0] == 0.0 and wilson_interval(10, 10)[1] == 1.0
    assert wilson_interval(0, 0) is None


def test_mean():
    assert mean([1, 2, 3]) == 2
    assert mean([]) is None


def test_bootstrap_constant_values():
    assert bootstrap_mean_ci([1.0, 1.0, 1.0]) == [1.0, 1.0]


def test_bootstrap_is_deterministic_and_brackets_mean():
    values = [0, 1, 2, 3, -1, 2, 1]
    first = bootstrap_mean_ci(values)
    assert first == bootstrap_mean_ci(values)
    assert first[0] <= mean(values) <= first[1]
    assert bootstrap_mean_ci([]) is None
```

Run: `harness/.venv/bin/pytest harness/tests/test_stats.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Write `harness/src/matchlab/stats.py`**

```python
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
```

- [ ] **Step 3: Run the tests**

Run: `harness/.venv/bin/pytest harness/tests/test_stats.py -q`
Expected: `4 passed`.

- [ ] **Step 4: Commit**

```bash
git add harness/src/matchlab/stats.py harness/tests/test_stats.py
git commit -m "feat(harness): Wilson intervals and a seeded percentile bootstrap" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Experiments, reports and the Python API

**Covers:** tasks.md 7.1, 7.2, 7.4, 7.5, 7.6

**Files:**
- Create: `harness/src/matchlab/experiment.py`, `harness/src/matchlab/report.py`, `harness/tests/test_experiment.py`, `harness/tests/test_report.py`
- Modify: `harness/src/matchlab/__init__.py` (export the API)

**Interfaces:**
- Consumes: `load_profile` (Task 9); `match_seeds` (Task 10); `replay_and_compare` (Task 12); `run_matches`, `MatchResult` (Task 14); `mean`, `wilson_interval`, `bootstrap_mean_ci`, `BOOTSTRAP_RESAMPLES`, `BOOTSTRAP_SEED` (Task 15); `load_manifest`; `paths.runs_dir`.
- Produces:
  - `experiment.py`: `class ExperimentError(ValueError)`; `@dataclass(frozen=True) class Arm(name: str, profile: str, overrides: dict)`; `@dataclass(frozen=True) class Experiment(name: str, matches: int, base_seed: int, swap_sides: bool, timeout_s: float, arms: dict[str, Arm], source: Path | None)`; `@dataclass(frozen=True) class ArmResult(profile: str, profile_hash: str, matches: list[MatchResult])`; `@dataclass(frozen=True) class ExperimentResult(name: str, out_dir: Path, seeds: list[int], arms: dict[str, ArmResult], report: dict)`; `load_experiment(path: Path) -> Experiment`; `run_experiment(experiment: Experiment | str | Path, *, out_dir: Path | None = None, workers: int = 1, manifest: Manifest | None = None) -> ExperimentResult`.
  - `report.py`: `REPORT_SCHEMA = 1`; `OTHER_METRICS: tuple[str, ...]`; `focus_view(result: MatchResult) -> dict | None`; `build_report(experiment: Experiment, seeds: list[int], arms: dict[str, ArmResult], reproducibility: dict) -> dict`; `render_markdown(report: dict) -> str`; `write_report(out_dir: Path, report: dict) -> None`.
  - The `reproducibility` dict: `{"checked_run": "A/0000-normal", "status": "identical" | "differs" | "not-checked", "first_difference": dict | None, "skipped_prefixes": list[str], "reason": str | None}`.
  - `matchlab.__init__` exports `run_experiment`, `run_matches`, `load_profile`, `load_experiment`.

Experiment file format:
```toml
name = "noise-check"     # letters, digits, _ and -; output folder runs/<name>/
matches = 10             # N, the number of seeds
base_seed = 42
swap_sides = false       # optional, default false
timeout_s = 3600         # optional, default 3600

[arms.A]
profile = "default"      # preset name or a path relative to this file

[arms.B]
profile = "default"
[arms.B.overrides.server]
player_rand = 0
```

After both arms, the experiment replays arm A's first match (first seed, normal sides) into `<out>/repro-A-0000` and compares the game logs. The report shows the result.

- [ ] **Step 1: Write the failing report tests `harness/tests/test_report.py`**

```python
from pathlib import Path

from matchlab.experiment import Arm, ArmResult, Experiment
from matchlab.report import build_report, render_markdown
from matchlab.runner import MatchResult


def metrics(gl, gr):
    side = {"team": "T", "shots": 3, "passes": 10, "pass_completion": 0.8, "interceptions": 2, "tackles": 1,
            "fouls": 0, "event_possession_share": 0.5}
    return {"schema": 1, "sides": {"left": {**side, "goals": gl, "goal_difference": gl - gr},
                                   "right": {**side, "goals": gr, "goal_difference": gr - gl}}}


def result(index, gl, gr, swapped=False, status="ok", missed=0):
    return MatchResult(index, swapped, 100 + index, Path(f"/x/{index}"), status,
                       metrics(gl, gr) if status == "ok" else None, "not-checked", missed)


EXP = Experiment("demo", 10, 42, False, 3600.0,
                 {"A": Arm("A", "default", {}), "B": Arm("B", "default", {"server": {"x": 0}})}, None)
REPRO = {"checked_run": "A/0000-normal", "status": "identical", "first_difference": None,
         "skipped_prefixes": [], "reason": None}


def arms(a_results, b_results):
    return {"A": ArmResult("default", "a" * 64, a_results), "B": ArmResult("default", "b" * 64, b_results)}


def test_rates_have_wilson_intervals():
    a = [result(i, 1, 0) for i in range(7)] + [result(7, 0, 0), result(8, 1, 1), result(9, 0, 2)]
    report = build_report(EXP, list(range(10)), arms(a, a), REPRO)
    arm = report["arms"]["A"]
    assert arm["win"]["rate"] == 0.7 and arm["draw"]["rate"] == 0.2 and arm["loss"]["rate"] == 0.1
    assert arm["win"]["ci95"][0] < 0.7 < arm["win"]["ci95"][1]
    assert report["paired_goal_difference"]["mean_difference"] == 0
    assert report["reproducibility"]["status"] == "identical"


def test_swapped_matches_use_the_focus_team():
    a = [result(0, 0, 2, swapped=True)]   # focus team plays on the right and wins 2-0
    report = build_report(EXP, [1], arms(a, a), REPRO)
    assert report["arms"]["A"]["goal_difference_mean"] == 2


def test_failed_pairs_are_excluded():
    a = [result(0, 1, 0), result(1, 1, 0)]
    b = [result(0, 0, 0), result(1, 0, 0, status="timeout")]
    report = build_report(EXP, [1, 2], arms(a, b), REPRO)
    paired = report["paired_goal_difference"]
    assert paired["pairs"] == 1 and paired["excluded"] == 1 and paired["mean_difference"] == -1
    assert report["arms"]["B"]["failed"] == {"timeout": 1}


def test_missed_cycles_are_counted():
    a = [result(0, 1, 0, missed=3), result(1, 1, 0), result(2, 0, 0, missed=1)]
    report = build_report(EXP, [1, 2, 3], arms(a, a), REPRO)
    assert report["arms"]["A"]["missed_cycles"] == {"matches": 2, "total": 4}
    assert "Missed cycles" in render_markdown(report)


def test_no_pairs_still_reports():
    a = [result(0, 1, 0, status="error")]
    not_checked = {**REPRO, "status": "not-checked", "reason": "the original match ended with status error"}
    report = build_report(EXP, [1], arms(a, a), not_checked)
    assert report["paired_goal_difference"]["mean_difference"] is None
    text = render_markdown(report)
    assert "n/a" in text and "not-checked" in text and "status error" in text


def test_report_is_deterministic():
    a = [result(i, i % 3, 1) for i in range(5)]
    b = [result(i, (i + 1) % 3, 1) for i in range(5)]
    first = build_report(EXP, list(range(5)), arms(a, b), REPRO)
    second = build_report(EXP, list(range(5)), arms(a, b), REPRO)
    assert first == second
    assert render_markdown(first) == render_markdown(second)
    assert "B minus A" in render_markdown(first)
```

- [ ] **Step 2: Write the failing experiment tests `harness/tests/test_experiment.py`**

```python
import json

import pytest

from matchlab import run_experiment
from matchlab.experiment import ExperimentError, load_experiment
from matchlab.profile import load_profile


def write_exp(tmp_path, body):
    path = tmp_path / "exp.toml"
    path.write_text(body)
    return path


BODY = '''name = "demo"
matches = 2
base_seed = 42
timeout_s = 30
[arms.A]
profile = "short"
[arms.B]
profile = "short"
[arms.B.overrides.server]
player_rand = 0
'''


def test_load_and_arm_override(tmp_path):
    exp = load_experiment(write_exp(tmp_path, BODY))
    assert exp.matches == 2 and exp.swap_sides is False
    b = load_profile(exp.arms["B"].profile, overrides=exp.arms["B"].overrides)
    assert b.data["server"]["player_rand"] == 0
    assert b.hash != load_profile("short").hash


@pytest.mark.parametrize("change, message", [
    (("matches = 2", "matches = 0"), "matches"),
    (("[arms.B]", "[arms.C]"), "arms A and B"),
    (('name = "demo"', 'name = "bad name"'), "name"),
    (("[arms.B.overrides.server]", "[arms.B.overrides.noise]"), "overrides"),
])
def test_bad_experiments(tmp_path, change, message):
    with pytest.raises(ExperimentError, match=message):
        load_experiment(write_exp(tmp_path, BODY.replace(*change)))


def test_run_experiment_with_fake_testbed(fake_testbed, tmp_path):
    out = tmp_path / "out"
    result = run_experiment(write_exp(tmp_path, BODY), out_dir=out, manifest=fake_testbed)
    report = json.loads((out / "report.json").read_text())
    assert (out / "report.md").is_file()
    assert report == result.report
    assert report["seeds"] == [737161366, 1416715386]
    assert report["paired_goal_difference"]["pairs"] == 2
    assert report["reproducibility"]["status"] == "identical"
    assert report["reproducibility"]["checked_run"] == "A/0000-normal"
    assert (out / "repro-A-0000" / "match.rcg.gz").is_file()
    assert json.loads((out / "A" / "0000-normal" / "run.json").read_text())["reproducibility"] == "identical"
    assert result.arms["A"].matches[0].reproducibility == "identical"
    assert result.arms["A"].profile_hash == load_profile("short").hash
    assert len(result.arms["B"].matches) == 2 and (out / "B" / "0001-normal" / "metrics.json").is_file()


def test_failed_original_is_not_checked(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "fail")
    result = run_experiment(write_exp(tmp_path, BODY), out_dir=tmp_path / "out", manifest=fake_testbed)
    assert result.report["reproducibility"]["status"] == "not-checked"
    assert "status error" in result.report["reproducibility"]["reason"]


def test_failed_replay_is_not_checked(fake_testbed, tmp_path, monkeypatch):
    import matchlab.experiment as experiment_mod

    def broken_replay(*args, **kwargs):
        raise RuntimeError("the replay did not finish (timeout)")

    monkeypatch.setattr(experiment_mod, "replay_and_compare", broken_replay)
    result = run_experiment(write_exp(tmp_path, BODY), out_dir=tmp_path / "out", manifest=fake_testbed)
    assert result.report["reproducibility"]["status"] == "not-checked"
    assert "did not finish" in result.report["reproducibility"]["reason"]


def test_existing_experiment_folder_is_refused(fake_testbed, tmp_path):
    (tmp_path / "out").mkdir()
    with pytest.raises(ExperimentError, match="already exists"):
        run_experiment(write_exp(tmp_path, BODY), out_dir=tmp_path / "out", manifest=fake_testbed)
```

Run: `harness/.venv/bin/pytest harness/tests/test_report.py harness/tests/test_experiment.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `harness/src/matchlab/experiment.py`**

```python
"""Paired A/B experiments over two arm profiles."""

from __future__ import annotations

import dataclasses
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .manifest import Manifest, load_manifest
from .profile import load_profile
from .repro import replay_and_compare
from .runner import MatchResult, run_matches
from .seeds import match_seeds

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_OVERRIDE_SECTIONS = frozenset({"match", "server", "player", "teams"})
_KEYS = frozenset({"name", "matches", "base_seed", "swap_sides", "timeout_s", "arms"})


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


def _int(raw: dict, key: str, minimum: int) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ExperimentError(f"{key}: must be a whole number of {minimum} or more")
    return value


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
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ExperimentError("timeout_s: must be a number of seconds greater than 0")
    arms_raw = raw.get("arms", {})
    if not isinstance(arms_raw, dict) or set(arms_raw) != {"A", "B"}:
        raise ExperimentError("define exactly two arms A and B ([arms.A] and [arms.B])")
    arms = {}
    for key in ("A", "B"):
        entry = arms_raw[key]
        profile = entry.get("profile") if isinstance(entry, dict) else None
        if not isinstance(profile, str) or not profile:
            raise ExperimentError(f"arms.{key}.profile: name a profile")
        overrides = entry.get("overrides", {})
        bad = sorted(set(overrides) - _OVERRIDE_SECTIONS)
        if bad:
            raise ExperimentError(f"arms.{key}.overrides: unknown section(s): {', '.join(bad)}")
        arms[key] = Arm(key, profile, overrides)
    return Experiment(name, _int(raw, "matches", 1), _int(raw, "base_seed", 0), swap, float(timeout), arms, path)


def _replay_first_match(first: MatchResult, profile, out: Path, manifest: Manifest, timeout_s: float) -> dict:
    result = {"checked_run": "A/0000-normal", "status": "not-checked", "first_difference": None,
              "skipped_prefixes": [], "reason": None}
    if first.status != "ok":
        result["reason"] = f"the original match ended with status {first.status}"
        return result
    try:
        repro = replay_and_compare(profile, first.match_seed, first.run_dir, out / "repro-A-0000", manifest,
                                   timeout_s=timeout_s, profile_hash=profile.hash)
    except RuntimeError as exc:
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
```

- [ ] **Step 4: Write `harness/src/matchlab/report.py`**

```python
"""Experiment reports: JSON data and a Markdown summary (no time stamps, so reports are reproducible)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .experiment import ArmResult, Experiment
from .runner import MatchResult
from .stats import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, bootstrap_mean_ci, mean, wilson_interval

REPORT_SCHEMA = 1
OTHER_METRICS = ("shots", "passes", "pass_completion", "interceptions", "tackles", "fouls",
                 "event_possession_share")


def focus_view(result: MatchResult) -> dict | None:
    """Values from the view of the focus team (the arm profile's left team)."""
    if result.status != "ok" or result.metrics is None:
        return None
    focus, other = ("right", "left") if result.swapped else ("left", "right")
    sides = result.metrics["sides"]
    view = {"goal_difference": sides[focus]["goals"] - sides[other]["goals"]}
    view.update({key: sides[focus][key] for key in OTHER_METRICS})
    return view


def _rate(k: int, n: int) -> dict:
    return {"count": k, "rate": k / n if n else None, "ci95": wilson_interval(k, n)}


def _arm(arm: ArmResult) -> dict:
    views = [v for v in (focus_view(m) for m in arm.matches) if v is not None]
    gd = [v["goal_difference"] for v in views]
    n = len(views)
    return {
        "profile": arm.profile,
        "profile_hash": arm.profile_hash,
        "matches": len(arm.matches),
        "ok": n,
        "failed": dict(sorted(Counter(m.status for m in arm.matches if m.status != "ok").items())),
        "missed_cycles": {"matches": sum(1 for m in arm.matches if m.missed_cycles > 0),
                          "total": sum(m.missed_cycles for m in arm.matches)},
        "goal_difference_mean": mean(gd),
        "win": _rate(sum(1 for x in gd if x > 0), n),
        "draw": _rate(sum(1 for x in gd if x == 0), n),
        "loss": _rate(sum(1 for x in gd if x < 0), n),
        "metrics_mean": {key: mean([v[key] for v in views if v[key] is not None]) for key in OTHER_METRICS},
    }


def build_report(experiment: Experiment, seeds: list[int], arms: dict[str, ArmResult],
                 reproducibility: dict) -> dict:
    by_key = {key: {(m.index, m.swapped): focus_view(m) for m in arm.matches} for key, arm in arms.items()}
    keys = sorted(set(by_key["A"]) | set(by_key["B"]))
    diffs = [by_key["B"][k]["goal_difference"] - by_key["A"][k]["goal_difference"]
             for k in keys if by_key["A"].get(k) is not None and by_key["B"].get(k) is not None]
    return {
        "schema": REPORT_SCHEMA,
        "experiment": experiment.name,
        "base_seed": experiment.base_seed,
        "seeds": list(seeds),
        "swap_sides": experiment.swap_sides,
        "matches_per_arm": len(seeds) * (2 if experiment.swap_sides else 1),
        "focus_team": "the arm profile's left team (also in swapped matches)",
        "arms": {key: _arm(arms[key]) for key in sorted(arms)},
        "paired_goal_difference": {
            "direction": "B minus A",
            "pairs": len(diffs),
            "excluded": len(keys) - len(diffs),
            "mean_difference": mean(diffs),
            "ci95": bootstrap_mean_ci(diffs),
            "method": f"percentile bootstrap, {BOOTSTRAP_RESAMPLES} resamples, seed {BOOTSTRAP_SEED}",
        },
        "reproducibility": dict(reproducibility),
    }


def _num(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _ci(ci) -> str:
    return "n/a" if ci is None else f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def _rate_text(rate: dict) -> str:
    return f"{_num(rate['rate'])} {_ci(rate['ci95'])}"


def render_markdown(report: dict) -> str:
    paired = report["paired_goal_difference"]
    repro = report["reproducibility"]
    lines = [
        f"# Experiment report: {report['experiment']}",
        "",
        f"- Matches per arm: {report['matches_per_arm']} (swap sides: {'yes' if report['swap_sides'] else 'no'})",
        f"- Base seed: {report['base_seed']}",
        f"- All values use the view of the focus team: {report['focus_team']}.",
        "",
        "## Paired goal difference (B minus A)",
        "",
        f"- Pairs used: {paired['pairs']} (excluded: {paired['excluded']})",
        f"- Mean difference: {_num(paired['mean_difference'])}",
        f"- 95% confidence interval: {_ci(paired['ci95'])} ({paired['method']})",
        "",
        "## Arms",
        "",
        "| Arm | Profile | Hash | OK / total | Missed cycles (matches) | Mean goal difference "
        "| Win (95% CI) | Draw (95% CI) | Loss (95% CI) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, arm in report["arms"].items():
        lines.append(
            f"| {key} | {arm['profile']} | `{arm['profile_hash']}` | {arm['ok']} / {arm['matches']} | "
            f"{arm['missed_cycles']['matches']} | {_num(arm['goal_difference_mean'])} | {_rate_text(arm['win'])} | "
            f"{_rate_text(arm['draw'])} | {_rate_text(arm['loss'])} |")
    lines += ["", "## Other metrics (mean per match)", "",
              "| Metric | " + " | ".join(report["arms"]) + " |",
              "|---|" + "---|" * len(report["arms"])]
    for metric in OTHER_METRICS:
        lines.append(f"| {metric} | " + " | ".join(_num(a["metrics_mean"][metric]) for a in report["arms"].values())
                     + " |")
    failed = {k: a["failed"] for k, a in report["arms"].items() if a["failed"]}
    lines += ["", "## Failed matches", ""]
    lines += [f"- Arm {k}: " + ", ".join(f"{s}: {c}" for s, c in v.items()) for k, v in failed.items()] or ["- None"]
    lines += ["", "## Reproducibility", "",
              f"- Replayed run: {repro['checked_run']}",
              f"- Result: {repro['status']}"]
    if repro.get("reason"):
        lines.append(f"- Reason: {repro['reason']}")
    if repro.get("first_difference"):
        d = repro["first_difference"]
        lines.append(f"- First difference: line {d['line']}, cycle {d['cycle']}")
    if repro.get("skipped_prefixes"):
        lines.append(f"- Skipped line prefixes: {', '.join(repro['skipped_prefixes'])}")
    lines += ["", "## Seeds", "", ", ".join(str(s) for s in report["seeds"]), ""]
    return "\n".join(lines)


def write_report(out_dir: Path, report: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (out_dir / "report.md").write_text(render_markdown(report))
```

- [ ] **Step 5: Export the API in `harness/src/matchlab/__init__.py`**

```python
"""matchlab: build the RoboCup testbed, run seeded matches, report A/B experiments."""

from .experiment import load_experiment, run_experiment
from .profile import load_profile
from .runner import run_matches

__all__ = ["load_experiment", "load_profile", "run_experiment", "run_matches"]
__version__ = "0.1.0"
```

- [ ] **Step 6: Run all tests**

Run: `harness/.venv/bin/pytest harness/tests -q`
Expected: all pass (the report and experiment tests add `15 passed`; no failures elsewhere).

- [ ] **Step 7: Commit**

```bash
git add harness/src/matchlab/experiment.py harness/src/matchlab/report.py harness/src/matchlab/__init__.py harness/tests/test_experiment.py harness/tests/test_report.py
git commit -m "feat(harness): paired A/B experiments with a replay check and deterministic reports" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: CLI subcommands `run`, `experiment`, `check-repro`

**Covers:** tasks.md 8.1

**Files:**
- Modify: `harness/src/matchlab/cli.py`
- Create: `harness/tests/test_cli.py`

**Interfaces:**
- Consumes: `run_matches`, `run_experiment`, `check_reproducibility`, `load_profile`, `load_manifest`, `match_seeds`, error classes.
- Produces: `matchlab run --profile P --matches N --seed S --out DIR [--workers W] [--timeout T] [--swap-sides]` (exit 0 when all matches are `ok`, else 1); `matchlab experiment FILE [--out DIR] [--workers W]` (exit 0); `matchlab check-repro --profile P --seed S --out DIR [--timeout T]` (exit 0 for `identical`, 1 for `differs`). Errors print `error: <message>` and exit 2.

- [ ] **Step 1: Write the failing tests `harness/tests/test_cli.py`**

```python
from pathlib import Path

import matchlab.cli as cli
from matchlab.repro import ReproResult


def test_experiment_calls_the_api(monkeypatch, tmp_path, capsys):
    seen = {}

    def fake_run_experiment(path, *, out_dir=None, workers=1, manifest=None):
        seen.update(path=path, out_dir=out_dir, workers=workers)

        class R:
            out_dir = tmp_path
            report = {"paired_goal_difference": {"mean_difference": 0.5, "ci95": [0.1, 0.9], "pairs": 4},
                      "reproducibility": {"status": "identical", "checked_run": "A/0000-normal"}}
        return R()

    monkeypatch.setattr(cli, "run_experiment", fake_run_experiment)
    assert cli.main(["experiment", "exp.toml", "--out", str(tmp_path), "--workers", "2"]) == 0
    assert seen == {"path": Path("exp.toml"), "out_dir": tmp_path, "workers": 2}
    out = capsys.readouterr().out
    assert "report.md" in out and "Reproducibility (A/0000-normal replayed): identical" in out


def test_ctrl_c_exits_130(monkeypatch, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_experiment", interrupted)
    assert cli.main(["experiment", "exp.toml"]) == 130
    assert "cancelled" in capsys.readouterr().err


def test_check_repro_exit_codes(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "load_manifest", lambda: type("M", (), {"teams": {"helios": None}})())
    monkeypatch.setattr(cli, "check_reproducibility",
                        lambda *a, **k: ReproResult("differs", {"line": 3, "cycle": 2, "a": "x", "b": "y"}, ()))
    assert cli.main(["check-repro", "--profile", "short", "--seed", "1", "--out", str(tmp_path / "r")]) == 1


def test_errors_exit_2(capsys):
    assert cli.main(["run", "--profile", "no-such-profile", "--seed", "1", "--out", "x"]) == 2
    assert capsys.readouterr().err.startswith("error: ")
```

Note: `test_errors_exit_2` needs a manifest or must fail before loading it. `_cmd_run` loads the profile **before** the manifest, with `known_teams=None`, then checks teams against the manifest. A missing profile then raises `ProfileError` first.

Run: `harness/.venv/bin/pytest harness/tests/test_cli.py -q` → FAIL.

- [ ] **Step 2: Extend `harness/src/matchlab/cli.py`**

Add these imports at the top:
```python
from pathlib import Path

from .experiment import ExperimentError, run_experiment
from .manifest import load_manifest
from .ports import PortInUseError
from .profile import ProfileError, load_profile
from .repro import check_reproducibility
from .runner import run_matches
from .seeds import match_seeds
```

Add the handlers:
```python
def _profile_for_testbed(ref: str):
    load_profile(ref)  # report profile errors before touching the testbed
    manifest = load_manifest()
    return load_profile(ref, known_teams=manifest.teams.keys()), manifest


def _cmd_run(args: argparse.Namespace) -> int:
    profile, manifest = _profile_for_testbed(args.profile)
    results = run_matches(profile, match_seeds(args.seed, args.matches), out_dir=args.out, manifest=manifest,
                          workers=args.workers, timeout_s=args.timeout, swap_sides=args.swap_sides)
    for r in results:
        gd = r.metrics["sides"]["left"]["goal_difference"] if r.metrics else "n/a"
        print(f"{r.run_dir.name}: {r.status} (seed {r.match_seed}, left goal difference {gd}, "
          f"missed cycles {r.missed_cycles})")
    return 0 if all(r.status == "ok" for r in results) else 1


def _cmd_experiment(args: argparse.Namespace) -> int:
    result = run_experiment(args.file, out_dir=args.out, workers=args.workers)
    paired = result.report["paired_goal_difference"]
    repro = result.report["reproducibility"]
    print(f"Paired goal difference (B minus A): {paired['mean_difference']} "
          f"95% CI {paired['ci95']} over {paired['pairs']} pairs")
    print(f"Reproducibility ({repro['checked_run']} replayed): {repro['status']}")
    print(f"Report: {result.out_dir / 'report.md'}")
    return 0


def _cmd_check_repro(args: argparse.Namespace) -> int:
    profile, manifest = _profile_for_testbed(args.profile)
    result = check_reproducibility(profile, args.seed, args.out, manifest, timeout_s=args.timeout)
    print(f"Reproducibility: {result.status}")
    if result.first_difference:
        d = result.first_difference
        print(f"First difference at line {d['line']} (cycle {d['cycle']}):\n  a: {d['a']}\n  b: {d['b']}")
    if result.skipped:
        print(f"Skipped line prefixes: {', '.join(result.skipped)}")
    return 0 if result.status == "identical" else 1
```

In `_parser()`, after the `build` parser, add:
```python
    run = sub.add_parser("run", help="run N matches for one profile")
    run.add_argument("--profile", required=True, help="preset name or path to a profile TOML file")
    run.add_argument("--matches", type=int, default=1)
    run.add_argument("--seed", type=int, required=True, help="base seed; match seeds derive from it")
    run.add_argument("--out", type=Path, required=True, help="output folder for the run folders")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--timeout", type=float, default=3600.0, help="seconds per match")
    run.add_argument("--swap-sides", action="store_true", help="also play each seed with the teams exchanged")
    run.set_defaults(handler=_cmd_run)

    exp = sub.add_parser("experiment", help="run a paired A/B experiment from a TOML file")
    exp.add_argument("file", type=Path)
    exp.add_argument("--out", type=Path, default=None, help="output folder (default runs/<name>)")
    exp.add_argument("--workers", type=int, default=1)
    exp.set_defaults(handler=_cmd_experiment)

    rep = sub.add_parser("check-repro", help="run one match twice and compare the game logs")
    rep.add_argument("--profile", required=True)
    rep.add_argument("--seed", type=int, required=True, help="the match seed")
    rep.add_argument("--out", type=Path, required=True)
    rep.add_argument("--timeout", type=float, default=3600.0)
    rep.set_defaults(handler=_cmd_check_repro)
```

Replace the `ERRORS` tuple and `main` with:
```python
ERRORS: tuple[type[Exception], ...] = (PinError, PatchError, BuildError, ManifestError, ProfileError,
                                       ExperimentError, PortInUseError, FileExistsError)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # run_matches has already stopped every running match before the interrupt reaches here.
        print("cancelled: all match processes were stopped", file=sys.stderr)
        return 130
```

- [ ] **Step 3: Run all tests**

Run: `harness/.venv/bin/pytest harness/tests -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add harness/src/matchlab/cli.py harness/tests/test_cli.py
git commit -m "feat(harness): add run, experiment and check-repro commands" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: End-to-end checks, demo experiment and README

**Covers:** tasks.md 8.2, 8.3, 8.4

**Files:**
- Create: `harness/tests/test_integration.py`, `testbed/experiments/demo-noise.toml`, `harness/README.md`

**Interfaces:**
- Consumes: everything above; the real testbed built in Task 6/7.

- [ ] **Step 1: Write the integration tests `harness/tests/test_integration.py`**

Task 8 decided fallback B (statistical reproducibility), so the test accepts `identical` or `differs` and checks that a difference names its line. The line marked `# identical path` is NOT part of the file.

```python
"""End-to-end tests on the real testbed. Skipped when .testbed/manifest.json is missing."""

import pytest

from matchlab.manifest import ManifestError, load_manifest
from matchlab.profile import load_profile
from matchlab.repro import check_reproducibility
from matchlab.runner import run_matches

pytestmark = pytest.mark.testbed


@pytest.fixture(scope="module")
def manifest():
    try:
        return load_manifest()
    except ManifestError:
        pytest.skip("testbed not built; run `matchlab build`")


def test_short_match_end_to_end(manifest, tmp_path):
    profile = load_profile("short", known_teams=manifest.teams.keys())
    [result] = run_matches(profile, [42], out_dir=tmp_path, manifest=manifest, timeout_s=900)
    assert result.status == "ok", (result.run_dir / "run.json").read_text()
    for name in ("profile.json", "run.json", "match.rcg.gz", "match.rcl.gz", "events.csv", "metrics.json"):
        assert (result.run_dir / name).is_file(), name
    assert result.metrics["schema"] == 1
    assert result.metrics["sides"]["left"]["team"] == "HELIOS_L"


def test_short_match_reproducibility(manifest, tmp_path):
    profile = load_profile("short", known_teams=manifest.teams.keys())
    result = check_reproducibility(profile, 42, tmp_path / "repro", manifest, timeout_s=900)
    assert result.status in ("identical", "differs")
    if result.status == "differs":
        assert result.first_difference["line"] >= 1
```

- [ ] **Step 2: Run the integration tests on the real testbed**

Run: `harness/.venv/bin/pytest harness/tests/test_integration.py -q -m testbed`
Expected: `2 passed` (each short match takes about 1–3 minutes).

- [ ] **Step 3: Write the demo experiment `testbed/experiments/demo-noise.toml`**

```toml
# Demo: does turning off random noise change the result of HELIOS vs HELIOS?
# Short matches and a small N, for this machine (4 cores, 3 GB RAM).
name = "demo-noise"
matches = 4
base_seed = 2026
timeout_s = 900

[arms.A]
profile = "../profiles/short.toml"

[arms.B]
profile = "../profiles/short.toml"

[arms.B.overrides.server]
ball_rand = 0
player_rand = 0
kick_rand = 0
prand_factor_l = 0
prand_factor_r = 0
kick_rand_factor_l = 0
kick_rand_factor_r = 0
wind_rand = 0
tackle_rand_factor = 0
dist_noise_rate = 0
focus_dist_noise_rate = 0
land_dist_noise_rate = 0
land_focus_dist_noise_rate = 0

[arms.B.overrides.player]
kick_rand_delta_factor = 0
```

- [ ] **Step 4: Run the demo experiment and check the report**

Run it in the background (8 short matches plus 1 replay; about 10–30 minutes) with the Bash tool's `run_in_background` option:
`harness/.venv/bin/matchlab experiment testbed/experiments/demo-noise.toml --out runs/demo-noise > /tmp/matchlab-demo.log 2>&1; echo "exit $?" >> /tmp/matchlab-demo.log`
Wait for it, then `cat /tmp/matchlab-demo.log`.
Expected: `Reproducibility (A/0000-normal replayed): <identical or the Task 8 result>`, `Report: runs/demo-noise/report.md` and `exit 0`. Open the report and check: two arms with different profile hashes; 4 seeds; `Pairs used: 4 (excluded: 0)` (or a listed reason for exclusions); a 95% confidence interval line; a missed-cycles column; a reproducibility section with the replay result. Copy the first 15 lines of `report.md` into the task report for the reviewer.

- [ ] **Step 5: Write `harness/README.md`**

```markdown
# matchlab

matchlab builds the RoboCup 2D testbed from pinned sources, runs seeded matches,
and reports paired A/B experiments. It is the measurement tool for the future
match engine.

## System dependencies

- A C++17 compiler, CMake 3.16 or later, autoconf, automake, libtool
- Boost headers, zlib, flex, bison, Git, curl access to GitHub and GitLab
- Python 3.11 or later

## Install

    python3 -m venv harness/.venv
    harness/.venv/bin/pip install -e 'harness[dev]'

## Build the testbed

    harness/.venv/bin/matchlab build --jobs 2

The build fetches each component in `testbed/pins.toml`, applies the patches in
`testbed/patches/<component>/`, and builds everything in `.testbed/`. It writes
nothing outside `.testbed/`. The file `.testbed/manifest.json` records the pins,
the patch checksums and the binary paths.

## Run matches

    harness/.venv/bin/matchlab run --profile short --matches 2 --seed 42 --out runs/try

Each match gets its own folder with `profile.json`, `run.json`, the compressed
game logs, `events.csv` (SPADL events from rcg2data) and `metrics.json`.

Profiles are TOML files in `testbed/profiles/`. Presets: `default`, `noise-off`,
`short`. A profile can extend another profile. The profile hash and the seed
identify a result.

## Run an A/B experiment

    harness/.venv/bin/matchlab experiment testbed/experiments/demo-noise.toml

Both arms play the same seeds. The report gives the paired difference in goal
difference (B minus A) with a 95% bootstrap confidence interval, and win, draw
and loss rates with Wilson intervals. Values use the view of the focus team
(the arm profile's left team).

## Reproducibility

    harness/.venv/bin/matchlab check-repro --profile short --seed 42 --out runs/repro-42

The check runs one match twice and compares the game logs byte for byte.
Every experiment also replays arm A's first seed once and reports the result.

The harness runs the server in synch mode and starts the teams one after the
other: the right team starts only when the left team's 11 players and coach
have connected. A client that answers too slowly makes the server skip it for
one cycle ("Someone missed a cycle"); such a match is not reproducible.
`run.json` and the report count these missed cycles.

Status: **differs** (statistical reproducibility). The same profile and seed
give the same distribution of results, not the same game log. The patched
server makes everything before kick-off identical: every client connects at
step 0 and kick-off is at step 300. After kick-off, the order and timing of
client commands and the server's shared random generator still vary, even
with all noise set to 0. Coaches stay on by default; they are not the cause.
The check skips two line prefixes that hold no play data: `(server_param`
(the run's log folder paths) and `(msg ` (a result line with a time stamp).
Exact replay is planned for our own engine.

## Python API

    from matchlab import load_profile, run_matches, run_experiment
    result = run_experiment("testbed/experiments/demo-noise.toml", workers=1)
    print(result.report["paired_goal_difference"])
```

Replace the `Status:` placeholder line with the real Task 8 result before you commit.

- [ ] **Step 6: Run the full test suite**

Run: `harness/.venv/bin/pytest harness/tests -q`
Expected: all pass (integration tests included, because the testbed is built).

- [ ] **Step 7: Commit**

```bash
git add harness/tests/test_integration.py testbed/experiments/demo-noise.toml harness/README.md
git commit -m "test(harness): end-to-end testbed checks, demo experiment and README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
