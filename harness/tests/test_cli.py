from pathlib import Path

import pytest

import matchlab.cli as cli
from matchlab.repro import ReproError, ReproResult


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
    assert "cancelled: all match processes were stopped" in capsys.readouterr().err


def test_check_repro_exit_codes(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "load_manifest", lambda: type("M", (), {"teams": {"helios": None}})())
    monkeypatch.setattr(cli, "check_reproducibility",
                        lambda *a, **k: ReproResult("differs", {"line": 3, "cycle": 2, "a": "x", "b": "y"}, ()))
    assert cli.main(["check-repro", "--profile", "short", "--seed", "1", "--out", str(tmp_path / "r")]) == 1


def test_errors_exit_2(capsys):
    assert cli.main(["run", "--profile", "no-such-profile", "--seed", "1", "--out", "x"]) == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_unfinished_repro_run_exits_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "load_manifest", lambda: type("M", (), {"teams": {"helios": None}})())

    def unfinished(*a, **k):
        raise ReproError("run a did not finish (error: boom); see x")

    monkeypatch.setattr(cli, "check_reproducibility", unfinished)
    assert cli.main(["check-repro", "--profile", "short", "--seed", "1", "--out", str(tmp_path / "r")]) == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_zero_workers_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--profile", "short", "--seed", "1", "--out", str(tmp_path / "x"), "--workers", "0"])
    assert exc.value.code == 2
    assert "must be 1 or more" in capsys.readouterr().err


def test_zero_matches_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--profile", "short", "--seed", "1", "--out", str(tmp_path / "x"), "--matches", "0"])
    assert exc.value.code == 2
    assert "must be 1 or more" in capsys.readouterr().err


def test_non_positive_timeout_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["check-repro", "--profile", "short", "--seed", "1", "--out", str(tmp_path / "r"),
                  "--timeout", "0"])
    assert exc.value.code == 2
    assert "must be greater than 0" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["run", "--matches", "1"], ["check-repro"]])
@pytest.mark.parametrize("seed", ["-1", "2147483648", "abc"])
def test_seed_out_of_range_is_a_usage_error(command, seed, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([command[0], "--profile", "short", "--seed", seed, "--out", str(tmp_path / "x"), *command[1:]])
    assert exc.value.code == 2
    capsys.readouterr()


def test_seed_bounds_are_accepted():
    assert cli._seed("0") == 0
    assert cli._seed("2147483647") == 2147483647


def test_seed_help_texts_say_what_the_seed_is(capsys):
    for command, text in (("run", "base seed; match seeds derive from it"),
                          ("check-repro", "the match seed itself (not a base seed)")):
        with pytest.raises(SystemExit):
            cli.main([command, "--help"])
        assert " ".join(capsys.readouterr().out.split()).count(text) == 1


@pytest.mark.parametrize("value", ["inf", "nan"])
def test_non_finite_timeout_is_a_usage_error(value, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["check-repro", "--profile", "short", "--seed", "1", "--out", str(tmp_path / "r"),
                  "--timeout", value])
    assert exc.value.code == 2
    assert "must be greater than 0" in capsys.readouterr().err


def test_ctrl_c_during_build_says_cancelled(monkeypatch, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "load_pins", lambda path: {})
    monkeypatch.setattr(cli, "build_all", interrupted)
    assert cli.main(["build"]) == 130
    assert capsys.readouterr().err.strip() == "cancelled"
