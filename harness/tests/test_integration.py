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
    assert result.metrics["schema"] == 2
    assert result.metrics["sides"]["left"]["team"] == "HELIOS_L"


def test_short_match_reproducibility(manifest, tmp_path):
    profile = load_profile("short", known_teams=manifest.teams.keys())
    result = check_reproducibility(profile, 42, tmp_path / "repro", manifest, timeout_s=900)
    assert result.status in ("identical", "differs")
    if result.status == "differs":
        assert result.first_difference["line"] >= 1
