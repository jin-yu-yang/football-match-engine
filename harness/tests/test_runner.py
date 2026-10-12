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
