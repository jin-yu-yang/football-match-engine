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
    (ctx.work / "manifest.json").unlink(missing_ok=True)  # a failed build must not leave the old manifest
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
