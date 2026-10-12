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
