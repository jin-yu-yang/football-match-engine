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
    assert m["schema"] == 2
    assert (left["goals"], right["goals"]) == (2, 1)
    assert (left["goal_difference"], right["goal_difference"]) == (1, -1)
    assert (left["passes"], right["passes"]) == (2, 1)
    assert (left["interceptions"], right["interceptions"]) == (0, 1)
    assert left["ball_retention"] == pytest.approx(0.5)   # 1 successful pass, 1 ball lost to an interception
    assert right["ball_retention"] == pytest.approx(1.0)  # 1 successful pass, no losses
    assert (left["fouls"], right["fouls"]) == (1, 1)
    assert left["event_possession_share"] == pytest.approx(0.4)
    assert left["event_possession_share"] + right["event_possession_share"] == pytest.approx(1.0)
    assert left["team"] == "HELIOS_L"


def test_unsupported_metrics_are_absent():
    m = compute_metrics(final_score(FIX / "mini.rcg"), foul_counts(FIX / "mini.rcg"),
                        read_events(FIX / "mini.event.csv"))
    for side in m["sides"].values():
        assert not {"shots", "tackles", "pass_completion"} & set(side)


def _row(kind, side1, side2, success="true"):
    return {"Type": kind, "Side1": side1, "Unum1": "1", "Time1": "1", "Mode1": "play_on", "X1": "0", "Y1": "0",
            "Side2": side2, "Unum2": "2", "Time2": "2", "X2": "1", "Y2": "1", "Success": success}


def test_ball_retention_from_passes_and_losses():
    events = [_row("Pass", "left", "left")] * 3 + [_row("Interception", "left", "right")]
    m = compute_metrics(final_score(FIX / "mini.rcg"), {"left": 0, "right": 0}, events)
    assert m["sides"]["left"]["ball_retention"] == pytest.approx(0.75)


def test_no_passes_and_no_losses_gives_null(tmp_path):
    csv = tmp_path / "e.csv"
    csv.write_text((FIX / "mini.event.csv").read_text().splitlines()[0] + "\n")
    m = compute_metrics(final_score(FIX / "mini.rcg"), {"left": 0, "right": 0}, read_events(csv))
    assert m["sides"]["left"]["ball_retention"] is None
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


def test_extract_with_relative_run_dir(fake_testbed, tmp_path, monkeypatch):
    run_dir_with_log(tmp_path)
    monkeypatch.chdir(tmp_path)
    metrics = extract_and_measure(Path("run"), fake_testbed)
    assert metrics is not None
    assert (tmp_path / "run" / "metrics.json").is_file()
    assert json.loads((tmp_path / "run" / "run.json").read_text())["extraction"] == "ok"
