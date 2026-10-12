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
