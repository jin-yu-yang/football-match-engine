import gzip
import shutil
from pathlib import Path

import pytest

from matchlab.rcg import FinalScore, RcgError, compress_logs, final_score, foul_counts, game_log, show_cycle

MINI = Path(__file__).parent / "fixtures" / "mini.rcg"


def test_final_score_and_fouls():
    assert final_score(MINI) == FinalScore("HELIOS_L", "HELIOS_R", 2, 1)
    assert foul_counts(MINI) == {"left": 1, "right": 1}


def test_gzip_is_read(tmp_path):
    gz = tmp_path / "m.rcg.gz"
    with gzip.open(gz, "wb") as fh:
        fh.write(MINI.read_bytes())
    assert final_score(gz).left == 2


def test_no_team_line(tmp_path):
    bad = tmp_path / "bad.rcg"
    bad.write_text("ULG6\n(show 1 ((b) 0 0 0 0))\n")
    with pytest.raises(RcgError, match="no final score"):
        final_score(bad)


def test_show_cycle():
    assert show_cycle(b"(show 42 ((b) 0 0 0 0))\n") == 42
    assert show_cycle(b"(team 1 A B 0 0)\n") is None


def test_compress_logs_and_game_log(tmp_path):
    shutil.copy(MINI, tmp_path / "match.rcg")
    (tmp_path / "match.rcl").write_text("x\n")
    assert game_log(tmp_path) == tmp_path / "match.rcg"
    compress_logs(tmp_path)
    assert not (tmp_path / "match.rcg").exists()
    assert gzip.open(tmp_path / "match.rcg.gz").read() == MINI.read_bytes()
    assert (tmp_path / "match.rcl.gz").exists()
    assert game_log(tmp_path) == tmp_path / "match.rcg.gz"
