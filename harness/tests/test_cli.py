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
