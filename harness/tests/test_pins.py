import pytest

from matchlab import paths
from matchlab.pins import COMPONENTS, PinError, load_pins

GOOD_GIT = 'kind = "git"\nurl = "https://example.org/x.git"\ncommit = "' + "a" * 40 + '"\n'


def write(tmp_path, body):
    path = tmp_path / "pins.toml"
    path.write_text(body)
    return path


def all_components(entry):
    return "".join(f"[{name}]\n{entry}\n" for name in COMPONENTS)


def test_repo_pins_cover_every_component():
    pins = load_pins(paths.testbed_dir() / "pins.toml")
    assert set(pins) == set(COMPONENTS)
    assert pins["rcssserver"].kind == "tarball"
    assert pins["eigen"].tag == "3.4.0"
    assert pins["librcsc"].ref == "65e139327751f2f45d9b5a03b1f59fb5ca700cd2"


def test_rejects_branch(tmp_path):
    body = all_components(GOOD_GIT).replace(
        '[librcsc]\nkind = "git"', '[librcsc]\nbranch = "master"\nkind = "git"'
    )
    with pytest.raises(PinError, match="librcsc: branch names are not allowed"):
        load_pins(write(tmp_path, body))


def test_rejects_short_commit(tmp_path):
    body = all_components('kind = "git"\nurl = "u"\ncommit = "65e1393"\n')
    with pytest.raises(PinError, match="full 40-character"):
        load_pins(write(tmp_path, body))


def test_rejects_missing_component(tmp_path):
    body = "".join(f"[{name}]\n{GOOD_GIT}\n" for name in COMPONENTS[:-1])
    with pytest.raises(PinError, match="missing component.*rcg2data"):
        load_pins(write(tmp_path, body))


def test_rejects_tarball_without_checksum(tmp_path):
    body = all_components(GOOD_GIT).replace(
        '[rcssserver]\n' + GOOD_GIT, '[rcssserver]\nkind = "tarball"\nurl = "u"\nstrip = "x"\n'
    )
    with pytest.raises(PinError, match="rcssserver: tarball needs a 64-character sha256"):
        load_pins(write(tmp_path, body))


def test_rejects_both_commit_and_tag(tmp_path):
    body = all_components(GOOD_GIT + 'tag = "v1"\n')
    with pytest.raises(PinError, match="exactly one of commit or tag"):
        load_pins(write(tmp_path, body))
