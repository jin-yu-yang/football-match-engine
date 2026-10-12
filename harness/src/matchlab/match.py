"""Run one match: server and two teams in one process group, one run folder."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, TeamEntry
from .ports import PortSet, ensure_free, port_set, wait_until_bound
from .profile import SIDES, Profile
from .record import RUN_SCHEMA, write_record
from .seeds import team_seed

PLAYERS_PER_TEAM = 11
CONNECT_TIMEOUT_S = 60.0
# In synch mode, cycles before all 22 players connect take microseconds. The default
# connect_wait (300 cycles) would end at once and auto mode would kick off an empty match.
CONNECT_WAIT = 100_000_000
# Cycles between the 22nd player and kick-off: time for the last coach to connect.
KICK_OFF_WAIT = 300
MISSED_CYCLE = "Someone missed a cycle"
GAVE_UP = "Waiting too long for clients! Exiting"

_PLAYER = re.compile(r"player \((\S+) (\d+)\) connected\.")
_COACH = re.compile(r"online coach \((\S+)\) connected\.")


class MatchStartError(RuntimeError):
    """A team did not connect, or the server ended before the match started."""


class MatchCancelled(Exception):
    """The caller asked to stop the match."""


@dataclass(frozen=True)
class MatchRecord:
    run_dir: Path
    status: str
    error: str | None
    duration_s: float
    missed_cycles: int


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def server_args(profile: Profile, ports: PortSet, match_seed: int, log_dir: Path) -> list[str]:
    fixed = {
        "port": ports.player, "coach_port": ports.coach, "olcoach_port": ports.olcoach,
        "synch_mode": True, "auto_mode": True, "random_seed": match_seed,
        "connect_wait": CONNECT_WAIT, "kick_off_wait": KICK_OFF_WAIT,
        # rcssserver patch 0003: no step before all players and enabled coaches are connected
        "synch_wait_clients": 2 * PLAYERS_PER_TEAM + sum(1 for side in SIDES if profile.team(side)["coach"]),
        "game_logging": True, "text_logging": True,
        "game_log_dir": log_dir, "text_log_dir": log_dir,
        "game_log_fixed": True, "text_log_fixed": True,
        "game_log_fixed_name": "match", "text_log_fixed_name": "match",
        "game_log_compression": 0, "text_log_compression": 0, "game_log_version": 6,  # ULG6 text format
        "nr_normal_halfs": profile.data["match"]["halves"], "half_time": profile.data["match"]["half_time"],
    }
    args = [f"server::{k}={_fmt(v)}" for k, v in sorted(profile.data["server"].items())]
    args += [f"player::{k}={_fmt(v)}" for k, v in sorted(profile.data["player"].items())]
    args += [f"server::{k}={_fmt(v)}" for k, v in sorted(fixed.items())]
    return args


def team_command(entry: TeamEntry, team_cfg: dict, ports: PortSet) -> list[str]:
    cmd = [str(entry.start), "-h", "127.0.0.1", "-p", str(ports.player), "-P", str(ports.olcoach),
           "-t", team_cfg["name"]]
    if not team_cfg["coach"]:
        cmd.append("-C")
    return cmd


def connected(log_text: str, team_name: str) -> tuple[int, bool]:
    players = {m.group(2) for m in _PLAYER.finditer(log_text) if m.group(1) == team_name}
    coach = any(m.group(1) == team_name for m in _COACH.finditer(log_text))
    return len(players), coach


def wait_for_team(server_log: Path, team_cfg: dict, server: subprocess.Popen, *,
                  timeout_s: float | None = None, cancel: threading.Event | None = None) -> None:
    name = team_cfg["name"]
    timeout_s = CONNECT_TIMEOUT_S if timeout_s is None else timeout_s
    deadline = time.monotonic() + timeout_s
    while True:
        players, coach = connected(server_log.read_text(errors="replace"), name)
        if players >= PLAYERS_PER_TEAM and (coach or not team_cfg["coach"]):
            return
        if server.poll() is not None:
            raise MatchStartError(f"the server ended with exit code {server.returncode} before team {name} connected")
        if cancel is not None and cancel.is_set():
            raise MatchCancelled()
        if time.monotonic() > deadline:
            no_coach = "" if coach or not team_cfg["coach"] else " and no coach"
            raise MatchStartError(
                f"team {name} connected {players} of {PLAYERS_PER_TEAM} players{no_coach} within {timeout_s} s")
        time.sleep(0.05)


def _wait_server(server: subprocess.Popen, timeout_s: float, cancel: threading.Event | None) -> int | None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return server.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                raise MatchCancelled() from None
            if time.monotonic() > deadline:
                return None


def _env(lib_dirs, **extra: str) -> dict[str, str]:
    env = os.environ.copy()
    if lib_dirs:
        parts = [str(p) for p in lib_dirs] + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else [])
        env["LD_LIBRARY_PATH"] = ":".join(parts)
    env.update(extra)
    return env


def _tail(path: Path, lines: int = 5) -> str:
    if not path.exists():
        return ""
    return " | ".join(path.read_text(errors="replace").strip().splitlines()[-lines:])


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _kill_group(pgid: int, server: subprocess.Popen | None) -> None:
    for sig, wait_s in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if server is not None:
                server.poll()
            if not _group_alive(pgid):
                break
            time.sleep(0.05)
        if not _group_alive(pgid):
            break
    if server is not None:
        try:
            server.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def run_single_match(profile: Profile, *, match_seed: int, run_dir: Path, manifest: Manifest, slot: int = 0,
                     timeout_s: float = 3600.0, profile_hash: str | None = None, swapped: bool = False,
                     cancel: threading.Event | None = None) -> MatchRecord:
    ports = port_set(slot)
    ensure_free(ports)
    run_dir.mkdir(parents=True, exist_ok=False)
    home = run_dir / "home"
    home.mkdir()
    seeds = {side: team_seed(match_seed, side) for side in SIDES}
    (run_dir / "profile.json").write_text(json.dumps(profile.data, indent=2, sort_keys=True) + "\n")
    record = {
        "schema": RUN_SCHEMA,
        "profile_hash": profile_hash or profile.hash,
        "played_profile_hash": profile.hash,  # differs from profile_hash in swapped matches
        "swapped": swapped,
        "match_seed": match_seed,
        "team_seeds": seeds,
        "teams": {side: profile.team(side) for side in SIDES},
        "pins": manifest.pins(),
        "status": "running",
        "error": None,
        "duration_s": None,
        "missed_cycles": None,
        "reproducibility": "not-checked",
        "extraction": None,
    }
    write_record(run_dir, record)

    server_log_path = run_dir / "server.log"
    status, error = "error", None
    server: subprocess.Popen | None = None
    logs = []
    start = time.monotonic()
    try:
        server_log = server_log_path.open("wb")
        logs.append(server_log)
        server = subprocess.Popen(
            [str(manifest.rcssserver), *server_args(profile, ports, match_seed, run_dir)],
            cwd=run_dir, env=_env(manifest.rcssserver_lib_dirs, HOME=str(home)),
            stdout=server_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, process_group=0,
        )
        try:
            wait_until_bound(ports.player, proc=server)
        except RuntimeError as exc:
            raise MatchStartError(str(exc)) from exc
        for side in SIDES:
            team_cfg = profile.team(side)
            entry = manifest.teams[team_cfg["team"]]
            team_log = (run_dir / f"team-{side}.log").open("wb")
            logs.append(team_log)
            try:
                starter = subprocess.Popen(
                    team_command(entry, team_cfg, ports), cwd=entry.start.parent,
                    env=_env(entry.lib_dirs, RCSC_RANDOM_SEED=str(seeds[side])),
                    stdout=team_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, process_group=server.pid,
                )
            except OSError as exc:  # the server's process group is gone when the server already ended
                if server.poll() is not None:
                    raise MatchStartError(
                        f"the server ended with exit code {server.returncode} before the {side} team started") from exc
                raise MatchStartError(f"cannot start the {side} team: {exc}") from exc
            try:
                starter_code = starter.wait(timeout=60)
            except subprocess.TimeoutExpired as exc:
                raise MatchStartError(f"the {side} team start script did not exit within 60 s") from exc
            if starter_code != 0:
                raise MatchStartError(f"the {side} team start script exited with code {starter_code}")
            wait_for_team(server_log_path, team_cfg, server, cancel=cancel)
        code = _wait_server(server, timeout_s, cancel)
        if code is None:
            status, error = "timeout", f"the match did not end within {timeout_s} s"
        elif code == 0 and (run_dir / "match.rcg").is_file():
            status = "ok"
        else:
            error = f"the server ended with exit code {code}" + (
                "" if (run_dir / "match.rcg").is_file() else " and wrote no match.rcg")
    except MatchCancelled:
        status, error = "cancelled", "the match was cancelled"
    except MatchStartError as exc:
        error = str(exc)
    except KeyboardInterrupt:
        status, error = "cancelled", "the match was interrupted (Ctrl-C)"
        raise
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if server is not None:
            _kill_group(server.pid, server)
        for fh in logs:
            fh.close()
        log_text = server_log_path.read_text(errors="replace") if server_log_path.exists() else ""
        missed = log_text.count(MISSED_CYCLE)
        if status == "ok" and GAVE_UP in log_text:
            status, error = "error", "the server gave up waiting for clients"
        if status in ("error", "timeout") and error:
            error = f"{error}; server.log ends with: {_tail(server_log_path)}"
        duration = round(time.monotonic() - start, 3)
        record.update(status=status, error=error, duration_s=duration, missed_cycles=missed)
        write_record(run_dir, record)
    return MatchRecord(run_dir, status, error, duration, missed)
