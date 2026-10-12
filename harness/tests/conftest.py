"""Shared test fixtures: a fake testbed made of small scripts."""

import os
import stat
from pathlib import Path

import pytest

from matchlab.manifest import Manifest, TeamEntry

FIXTURES = Path(__file__).parent / "fixtures"

FAKE_SERVER = r'''#!/usr/bin/env python3
"""Fake rcssserver: binds the player port, echoes team connections, writes logs, exits."""
import os, socket, sys, time
from pathlib import Path
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
out = Path(os.environ["FAKE_OUT"])
port = args["server::port"]
(out / f"server-args-{port}.txt").write_text("\n".join(sys.argv[1:]) + "\n")
(out / f"server-home-{port}.txt").write_text(os.environ.get("HOME", ""))
connect_log = out / f"connect-{port}.log"
connect_log.unlink(missing_ok=True)  # a new match on this port starts with no connections
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", int(port)))
mode = os.environ.get("FAKE_SERVER_MODE", "ok")
if mode == "fail":
    time.sleep(0.3)
    sys.exit(3)
seen = 0
while True:
    lines = connect_log.read_text().splitlines() if connect_log.exists() else []
    for line in lines[seen:]:
        print(line, flush=True)
    seen = len(lines)
    if mode in ("ok", "gaveup") and sum("player (" in line for line in lines) >= 22:
        break
    time.sleep(0.05)
for _ in range(int(os.environ.get("FAKE_MISSED", "0"))):
    print("Someone missed a cycle at 10", flush=True)
if mode == "gaveup":
    print("Waiting too long for clients! Exiting", flush=True)
log_dir = Path(args["server::game_log_dir"])
score = os.environ.get("FAKE_SCORE", "1 0")
(log_dir / "match.rcg").write_text(
    "ULG6\n(team 1 A B 0 0)\n(playmode 120 foul_charge_l)\n(team 600 A B " + score + ")\n")
(log_dir / "match.rcl").write_text("")
'''

FAKE_START = '''#!/bin/sh
# Fake team start script: records its input, "connects" its players, leaves one background child.
echo "$RCSC_RANDOM_SEED $*" >> "$FAKE_OUT/teams.txt"
PORT=""; NAME=""; COACH=1
while [ $# -gt 0 ]; do
  case "$1" in
    -p) PORT="$2"; shift ;;
    -t) NAME="$2"; shift ;;
    -C) COACH=0 ;;
  esac
  shift
done
i=1
while [ "$i" -le "${FAKE_TEAM_PLAYERS:-11}" ]; do
  echo "A new (v18) player ($NAME $i) connected." >> "$FAKE_OUT/connect-$PORT.log"
  i=$((i + 1))
done
if [ "$COACH" = 1 ]; then
  echo "A new (v18) online coach ($NAME) connected." >> "$FAKE_OUT/connect-$PORT.log"
fi
sleep 300 &
echo $! >> "$FAKE_OUT/children.txt"
exit 0
'''

FAKE_RCG2DATA = r'''#!/usr/bin/env python3
"""Fake rcg2data: writes the fixture events next to the input log."""
import os, shutil, sys
from pathlib import Path
if os.environ.get("FAKE_RCG2DATA_MODE", "ok") == "fail":
    sys.exit(1)
src = Path(sys.argv[1])
base = src.name.removesuffix(".gz").removesuffix(".rcg")
shutil.copy(os.environ["FAKE_EVENTS"], src.parent / f"{base}.event.csv")
'''


def _script(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def fake_testbed(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    out = tmp_path / "fakeout"
    out.mkdir()
    monkeypatch.setenv("FAKE_OUT", str(out))
    monkeypatch.setenv("FAKE_EVENTS", str(FIXTURES / "mini.event.csv"))
    start = _script(bin_dir / "start.sh", FAKE_START)
    return Manifest(
        components={"rcssserver": {"url": "fake", "ref": "fake", "patches": []}},
        rcssserver=_script(bin_dir / "rcssserver", FAKE_SERVER),
        rcssserver_lib_dirs=(),
        rcg2data=_script(bin_dir / "rcg2data", FAKE_RCG2DATA),
        rcg2data_lib_dirs=(),
        teams={"helios": TeamEntry(start, ()), "cyrus": TeamEntry(start, ())},
    )


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat_file = Path(f"/proc/{pid}/stat")
    return not (stat_file.exists() and stat_file.read_text().split()[2] == "Z")
