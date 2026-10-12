"""Match profiles: TOML files with inheritance, validation and a stable hash."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import tomllib
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import profiles_dir

SIDES = ("left", "right")
SECTIONS = frozenset({"extends", "match", "server", "player", "teams"})
MATCH_DEFAULTS = {"halves": 2, "half_time": 300}
TEAM_KEYS = frozenset({"team", "name", "coach"})

NOISE_PARAMS: tuple[str, ...] = (
    "ball_rand", "player_rand", "kick_rand",
    "prand_factor_l", "prand_factor_r", "kick_rand_factor_l", "kick_rand_factor_r",
    "wind_rand", "tackle_rand_factor",
    "dist_noise_rate", "focus_dist_noise_rate", "land_dist_noise_rate", "land_focus_dist_noise_rate",
)
PLAYER_NOISE_PARAMS: tuple[str, ...] = ("kick_rand_delta_factor",)

# The harness sets these itself for every match.
RESERVED_SERVER = frozenset({
    "port", "coach_port", "olcoach_port", "synch_mode", "auto_mode", "random_seed",
    "connect_wait", "kick_off_wait", "synch_wait_clients",
    "game_logging", "text_logging", "game_log_dir", "text_log_dir",
    "game_log_fixed", "text_log_fixed", "game_log_fixed_name", "text_log_fixed_name",
    "game_log_compression", "text_log_compression", "game_log_version", "nr_normal_halfs", "half_time",
})
RESERVED_PLAYER = frozenset({"random_seed"})

_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_TEAM_NAME = re.compile(r"^[A-Za-z0-9_-]{1,15}$")


class ProfileError(ValueError):
    """A profile file is missing, malformed or invalid."""


def _canonical(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    return value


def profile_hash(data: dict) -> str:
    text = json.dumps(_canonical(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Profile:
    data: dict

    @property
    def hash(self) -> str:
        return profile_hash(self.data)

    @property
    def cycles(self) -> int:
        step_ms = self.data["server"].get("simulator_step", 100)
        return int(round(self.data["match"]["halves"] * self.data["match"]["half_time"] * 1000 / step_ms))

    def team(self, side: str) -> dict:
        return self.data["teams"][side]

    def swapped(self) -> "Profile":
        data = copy.deepcopy(self.data)
        data["teams"] = {"left": data["teams"]["right"], "right": data["teams"]["left"]}
        return Profile(data)


def _locate(ref: str | Path, base_dir: Path | None) -> Path:
    text = str(ref)
    if text.endswith(".toml") or "/" in text:
        path = Path(text)
        if not path.is_absolute():
            path = (base_dir or Path.cwd()) / path
        return path.resolve()
    return profiles_dir() / f"{text}.toml"


def _merge(base: dict, top: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _load_raw(path: Path, seen: tuple[Path, ...]) -> dict:
    if path in seen:
        chain = " -> ".join(str(p) for p in (*seen, path))
        raise ProfileError(f"profile inheritance loop: {chain}")
    if not path.is_file():
        raise ProfileError(f"profile not found: {path}")
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path.name}: invalid TOML: {exc}") from exc
    unknown = sorted(set(raw) - SECTIONS)
    if unknown:
        raise ProfileError(f"{path.name}: unknown section(s): {', '.join(unknown)}")
    parent = raw.pop("extends", None)
    if parent is None:
        return raw
    return _merge(_load_raw(_locate(parent, path.parent), (*seen, path)), raw)


def _check_scalar(where: str, value: Any) -> None:
    if isinstance(value, (dict, list)):
        raise ProfileError(f"{where}: value must be a number, a boolean or a word, not {type(value).__name__}")
    if isinstance(value, str) and (not value or any(ch.isspace() for ch in value)):
        raise ProfileError(f"{where}: text values must be one word without spaces")


def _params(raw: dict, section: str, reserved: frozenset[str]) -> dict:
    params = raw.get(section, {})
    if not isinstance(params, dict):
        raise ProfileError(f"[{section}] must be a table")
    for key, value in params.items():
        if not _KEY.match(key):
            raise ProfileError(f"{section}.{key}: parameter names use lower case, digits and _")
        if key in reserved:
            raise ProfileError(f"{section}.{key}: this parameter is reserved; the harness sets it")
        _check_scalar(f"{section}.{key}", value)
    return {k: _canonical(v) for k, v in sorted(params.items())}


def _match(raw: dict) -> dict:
    match = {**MATCH_DEFAULTS, **raw.get("match", {})}
    unknown = sorted(set(match) - set(MATCH_DEFAULTS))
    if unknown:
        raise ProfileError(f"[match]: unknown key(s): {', '.join(unknown)}")
    if not isinstance(match["halves"], int) or isinstance(match["halves"], bool) or match["halves"] < 1:
        raise ProfileError("match.halves: must be a whole number of 1 or more")
    if not isinstance(match["half_time"], (int, float)) or isinstance(match["half_time"], bool) \
            or match["half_time"] <= 0:
        raise ProfileError("match.half_time: must be a number of seconds greater than 0")
    return {k: _canonical(v) for k, v in sorted(match.items())}


def _teams(raw: dict, known_teams: Collection[str] | None) -> dict:
    teams = raw.get("teams", {})
    if set(teams) != set(SIDES):
        raise ProfileError("[teams]: set both teams.left and teams.right")
    out = {}
    for side in SIDES:
        entry = teams[side]
        unknown = sorted(set(entry) - TEAM_KEYS)
        if unknown:
            raise ProfileError(f"teams.{side}: unknown key(s): {', '.join(unknown)}")
        team = entry.get("team")
        if not isinstance(team, str) or not team:
            raise ProfileError(f"teams.{side}.team: name a team from the manifest")
        if known_teams is not None and team not in known_teams:
            raise ProfileError(f"teams.{side}: unknown team '{team}'; known teams: {', '.join(sorted(known_teams))}")
        name = entry.get("name", f"{team.upper()}_{side[0].upper()}"[:15])
        if not isinstance(name, str) or not _TEAM_NAME.match(name):
            raise ProfileError(f"teams.{side}.name: use 1 to 15 letters, digits, _ or -")
        coach = entry.get("coach", True)
        if not isinstance(coach, bool):
            raise ProfileError(f"teams.{side}.coach: must be true or false")
        out[side] = {"team": team, "name": name, "coach": coach}
    if out["left"]["name"] == out["right"]["name"]:
        raise ProfileError("teams: the left and right team names must differ")
    return out


def load_profile(ref: str | Path, *, overrides: dict | None = None,
                 known_teams: Collection[str] | None = None, base_dir: Path | None = None) -> Profile:
    raw = _load_raw(_locate(ref, base_dir), ())
    if overrides:
        unknown = sorted(set(overrides) - (SECTIONS - {"extends"}))
        if unknown:
            raise ProfileError(f"overrides: unknown section(s): {', '.join(unknown)}")
        raw = _merge(raw, overrides)
    data = {
        "match": _match(raw),
        "server": _params(raw, "server", RESERVED_SERVER),
        "player": _params(raw, "player", RESERVED_PLAYER),
        "teams": _teams(raw, known_teams),
    }
    return Profile(data)
