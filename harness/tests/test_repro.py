import json

from matchlab.profile import load_profile
from matchlab.repro import check_reproducibility, compare_rcg

A = b"ULG6\n(show 1 x)\n(show 2 x)\n(show 3 a)\n"


def test_identical(tmp_path):
    (tmp_path / "a").write_bytes(A)
    (tmp_path / "b").write_bytes(A)
    assert compare_rcg(tmp_path / "a", tmp_path / "b").status == "identical"


def test_first_difference_has_line_and_cycle(tmp_path):
    (tmp_path / "a").write_bytes(A)
    (tmp_path / "b").write_bytes(A.replace(b"(show 3 a)", b"(show 3 b)"))
    result = compare_rcg(tmp_path / "a", tmp_path / "b")
    assert result.status == "differs"
    assert result.first_difference["line"] == 4 and result.first_difference["cycle"] == 3


def test_shorter_file_differs(tmp_path):
    (tmp_path / "a").write_bytes(A)
    (tmp_path / "b").write_bytes(A[:-11])
    assert compare_rcg(tmp_path / "a", tmp_path / "b").first_difference["b"] == "<end of file>"


def test_long_line_offset_and_excerpts(tmp_path):
    before = b"(show 1 " + b"x" * 892           # 900 bytes before the differing byte
    (tmp_path / "a").write_bytes(before + b"X" + b"x" * 99 + b"\n")
    (tmp_path / "b").write_bytes(before + b"Y" + b"x" * 99 + b"\n")
    result = compare_rcg(tmp_path / "a", tmp_path / "b")
    assert result.status == "differs"
    assert result.first_difference["offset"] == 900
    assert "X" in result.first_difference["a"] and "Y" in result.first_difference["b"]
    assert len(result.first_difference["a"]) < 300


def test_skipped_prefix_is_listed(tmp_path):
    (tmp_path / "a").write_bytes(b"(stamp 1)\n" + A)
    (tmp_path / "b").write_bytes(b"(stamp 2)\n" + A)
    result = compare_rcg(tmp_path / "a", tmp_path / "b", skip_prefixes=(b"(stamp ",))
    assert result.status == "identical" and result.skipped == ("(stamp ",)


def test_check_with_fake_testbed(fake_testbed, tmp_path):
    result = check_reproducibility(load_profile("short"), 5, tmp_path / "repro", fake_testbed, slot=21, timeout_s=30)
    assert result.status == "identical"
    saved = json.loads((tmp_path / "repro" / "repro.json").read_text())
    assert saved["status"] == "identical"
    for run in ("a", "b"):
        record = json.loads((tmp_path / "repro" / run / "run.json").read_text())
        assert record["reproducibility"] == "identical"
        assert (tmp_path / "repro" / run / "match.rcg.gz").exists()
