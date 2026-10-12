from pathlib import Path

from matchlab.experiment import Arm, ArmResult, Experiment
from matchlab.report import build_report, render_markdown
from matchlab.runner import MatchResult


def metrics(gl, gr):
    side = {"team": "T", "passes": 10, "ball_retention": 0.8, "interceptions": 2,
            "fouls": 0, "event_possession_share": 0.5}
    return {"schema": 2, "sides": {"left": {**side, "goals": gl, "goal_difference": gl - gr},
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


def test_differs_is_explained_with_excerpts():
    differs = {"checked_run": "A/0000-normal", "status": "differs",
               "first_difference": {"line": 3, "cycle": None, "a": "x", "b": "y", "offset": 10},
               "skipped_prefixes": ["(server_param"], "reason": None}
    a = [result(0, 1, 0)]
    text = render_markdown(build_report(EXP, [1], arms(a, a), differs))
    assert ("- Note: the replay differs. In the testbed, reproducibility is statistical: the same profile "
            "and seed give the same distribution of results, not the same game log (design D5).") in text
    assert "cycle n/a" in text
    assert "- Run a: `x`" in text and "- Run b: `y`" in text
    assert "Byte offset: 10" in text


def test_report_is_deterministic():
    a = [result(i, i % 3, 1) for i in range(5)]
    b = [result(i, (i + 1) % 3, 1) for i in range(5)]
    first = build_report(EXP, list(range(5)), arms(a, b), REPRO)
    second = build_report(EXP, list(range(5)), arms(a, b), REPRO)
    assert first == second
    assert render_markdown(first) == render_markdown(second)
    assert "B minus A" in render_markdown(first)
