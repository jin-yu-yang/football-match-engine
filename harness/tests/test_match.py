import json
import socket
import threading
import time
from pathlib import Path

import pytest

import matchlab.match as match_mod
from conftest import alive
from matchlab.manifest import TeamEntry
from matchlab.match import connected, run_single_match, server_args, team_command
from matchlab.ports import PortInUseError, port_set
from matchlab.profile import load_profile
from matchlab.seeds import team_seed


def children(out):
    path = out / "children.txt"
    return [int(x) for x in path.read_text().split()] if path.exists() else []


def wait_dead(pids, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and any(alive(p) for p in pids):
        time.sleep(0.05)
    return not any(alive(p) for p in pids)


def record(run_dir):
    return json.loads((run_dir / "run.json").read_text())


def test_server_args_contain_profile_and_fixed_values(tmp_path):
    p = load_profile("short", overrides={"server": {"ball_rand": 0}})
    args = server_args(p, port_set(2), 99, tmp_path)
    assert "server::ball_rand=0" in args
    assert "server::penalty_shoot_outs=false" in args
    assert "server::half_time=30" in args and "server::nr_normal_halfs=2" in args
    assert "server::random_seed=99" in args and "server::synch_mode=true" in args
    assert "server::connect_wait=100000000" in args and "server::kick_off_wait=300" in args
    assert "server::synch_wait_clients=24" in args  # 22 players + 2 coaches
    no_coach = load_profile("short", overrides={"teams": {"right": {"coach": False}}})
    assert "server::synch_wait_clients=23" in server_args(no_coach, port_set(2), 99, tmp_path)
    assert "server::game_log_version=6" in args

    assert "server::port=16020" in args and "server::olcoach_port=16022" in args
    assert f"server::game_log_dir={tmp_path}" in args and "server::game_log_fixed_name=match" in args


def test_noise_off_reaches_the_server(tmp_path):
    args = server_args(load_profile("noise-off"), port_set(3), 1, tmp_path)
    assert "server::ball_rand=0" in args and "server::dist_noise_rate=0" in args
    assert "player::kick_rand_delta_factor=0" in args


def test_team_command(tmp_path):
    entry = TeamEntry(tmp_path / "start.sh", ())
    cmd = team_command(entry, {"team": "helios", "name": "HELIOS_L", "coach": False}, port_set(1))
    assert cmd == [str(tmp_path / "start.sh"), "-h", "127.0.0.1", "-p", "16010", "-P", "16012", "-t", "HELIOS_L", "-C"]


def test_connected_counts_players_and_coach():
    log = ("A new (v18) player (HELIOS_L 1) connected.\nA new (v18) player (HELIOS_L 2) connected.\n"
           "A new (v18) player (HELIOS_R 1) connected.\nA new (v18) online coach (HELIOS_L) connected.\n")
    assert connected(log, "HELIOS_L") == (2, True)
    assert connected(log, "HELIOS_R") == (1, False)


def test_ok_match_writes_run_folder_and_kills_children(fake_testbed, tmp_path):
    out = tmp_path / "fakeout"
    run_dir = tmp_path / "run"
    rec = run_single_match(load_profile("short"), match_seed=737161366, run_dir=run_dir,
                           manifest=fake_testbed, slot=11, timeout_s=30)
    assert rec.status == "ok", rec.error
    data = record(run_dir)
    assert data["status"] == "ok" and data["reproducibility"] == "not-checked" and data["missed_cycles"] == 0
    assert data["team_seeds"] == {"left": 1608858898, "right": 308656577}
    assert data["profile_hash"] == load_profile("short").hash
    assert json.loads((run_dir / "profile.json").read_text()) == load_profile("short").data
    assert (run_dir / "match.rcg").is_file()
    lines = (out / "teams.txt").read_text().splitlines()
    assert lines[0].startswith(f"{team_seed(737161366, 'left')} ") and "-t HELIOS_L" in lines[0]
    assert lines[1].startswith(f"{team_seed(737161366, 'right')} ") and "-t HELIOS_R" in lines[1]
    assert (out / f"server-home-{port_set(11).player}.txt").read_text() == str(run_dir / "home")
    assert wait_dead(children(out))


def test_missed_cycles_are_counted(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MISSED", "2")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=16, timeout_s=30)
    assert rec.status == "ok" and rec.missed_cycles == 2
    assert record(tmp_path / "run")["missed_cycles"] == 2


def test_server_that_gave_up_is_an_error(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "gaveup")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=19, timeout_s=30)
    assert rec.status == "error" and "gave up waiting for clients" in rec.error


def test_team_that_does_not_connect_is_an_error(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_TEAM_PLAYERS", "9")
    monkeypatch.setattr(match_mod, "CONNECT_TIMEOUT_S", 0.5)
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=17, timeout_s=30)
    assert rec.status == "error" and "HELIOS_L connected 9 of 11 players" in rec.error
    assert len((tmp_path / "fakeout" / "teams.txt").read_text().splitlines()) == 1  # right team never started
    assert wait_dead(children(tmp_path / "fakeout"))


def test_timeout_kills_everything(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "hang")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=12, timeout_s=1)
    assert rec.status == "timeout"
    assert record(tmp_path / "run")["status"] == "timeout"
    assert wait_dead(children(tmp_path / "fakeout"))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", port_set(12).player))  # the fake server released its port


def test_server_failure_is_error(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "fail")
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=13, timeout_s=30)
    assert rec.status == "error" and "exit code 3" in rec.error


def test_port_in_use_starts_nothing(fake_testbed, tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", port_set(14).player))
        with pytest.raises(PortInUseError):
            run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                             manifest=fake_testbed, slot=14, timeout_s=30)
    assert not list((tmp_path / "fakeout").glob("server-args-*"))


def test_cancel_stops_match(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "hang")
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    started = time.monotonic()
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                           manifest=fake_testbed, slot=18, timeout_s=60, cancel=cancel)
    assert rec.status == "cancelled" and time.monotonic() - started < 15
    assert wait_dead(children(tmp_path / "fakeout"))


def test_interrupt_kills_processes(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVER_MODE", "hang")

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt  # as if the user pressed Ctrl-C after the left team started

    monkeypatch.setattr(match_mod, "wait_for_team", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_single_match(load_profile("short"), match_seed=1, run_dir=tmp_path / "run",
                         manifest=fake_testbed, slot=15, timeout_s=30)
    assert wait_dead(children(tmp_path / "fakeout"))
    assert record(tmp_path / "run")["status"] == "cancelled"


def test_relative_run_dir(fake_testbed, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rec = run_single_match(load_profile("short"), match_seed=1, run_dir=Path("rel/run"),
                           manifest=fake_testbed, slot=18, timeout_s=30)
    assert rec.status == "ok", rec.error
    assert rec.run_dir.is_absolute()
    assert (tmp_path / "rel" / "run" / "match.rcg").is_file()
