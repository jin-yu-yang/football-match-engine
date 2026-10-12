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
    (("base_seed = 42", "base_seed = 2147483648"), "base_seed: must be a whole number from 0 to 2147483647"),
    (("base_seed = 42", "base_seed = -1"), "base_seed: must be a whole number from 0 to 2147483647"),
    (("timeout_s = 30", "timeout_s = inf"), "timeout_s"),
    (("timeout_s = 30", "timeout_s = nan"), "timeout_s"),
    (("[arms.B]", "[arms.C]"), "arms A and B"),
    (('name = "demo"', 'name = "bad name"'), "name"),
    (("[arms.B.overrides.server]", "[arms.B.overrides.noise]"), "overrides"),
    (("[arms.B.overrides.server]", "[arms.B.override.server]"), "arms.B: unknown key\\(s\\): override"),
    (('[arms.B.overrides.server]\nplayer_rand = 0\n', 'overrides = 5\n'), "arms.B.overrides: must be a table"),
])
def test_bad_experiments(tmp_path, change, message):
    with pytest.raises(ExperimentError, match=message):
        load_experiment(write_exp(tmp_path, BODY.replace(*change)))


def test_replay_os_error_is_not_checked(fake_testbed, tmp_path, monkeypatch):
    import matchlab.experiment as experiment_mod

    def unreadable_replay(*args, **kwargs):
        raise FileNotFoundError("x")

    monkeypatch.setattr(experiment_mod, "replay_and_compare", unreadable_replay)
    out = tmp_path / "out"
    result = run_experiment(write_exp(tmp_path, BODY), out_dir=out, manifest=fake_testbed)
    assert result.report["reproducibility"]["status"] == "not-checked"
    assert json.loads((out / "report.json").read_text())["reproducibility"]["status"] == "not-checked"


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


def test_largest_base_seed_is_accepted(tmp_path):
    exp = load_experiment(write_exp(tmp_path, BODY.replace("base_seed = 42", "base_seed = 2147483647")))
    assert exp.base_seed == 2147483647


def test_extraction_failed_original_is_still_replayed(tmp_path, monkeypatch):
    import matchlab.experiment as experiment_mod
    from matchlab.runner import MatchResult

    calls = []

    class Repro:
        status = "identical"
        first_difference = None
        skipped = ()

    def fake_replay(profile, seed, run_dir, out, manifest, **kwargs):
        calls.append((seed, run_dir))
        return Repro()

    monkeypatch.setattr(experiment_mod, "replay_and_compare", fake_replay)
    profile = type("P", (), {"hash": "h"})()
    first = MatchResult(0, False, 7, tmp_path / "run", "extraction-failed", None, "not-checked", 0)
    result = experiment_mod._replay_first_match(first, profile, tmp_path, None, 10.0)
    assert calls == [(7, tmp_path / "run")]
    assert result["status"] == "identical"
    timed_out = MatchResult(0, False, 7, tmp_path / "run", "timeout", None, "not-checked", 0)
    result = experiment_mod._replay_first_match(timed_out, profile, tmp_path, None, 10.0)
    assert len(calls) == 1 and result["status"] == "not-checked"
