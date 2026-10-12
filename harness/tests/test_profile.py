import pytest

from matchlab.profile import (NOISE_PARAMS, PLAYER_NOISE_PARAMS, Profile, ProfileError, load_profile,
                              profile_hash)


def write(path, text):
    path.write_text(text)
    return path


def test_default_preset_resolves():
    p = load_profile("default", known_teams={"helios", "cyrus"})
    assert p.data["match"] == {"halves": 2, "half_time": 300}
    assert p.team("left") == {"team": "helios", "name": "HELIOS_L", "coach": True}
    assert p.team("right")["name"] == "HELIOS_R"
    assert p.cycles == 6000


def test_extends_and_override(tmp_path):
    child = write(tmp_path / "child.toml", 'extends = "default"\n[server]\nball_rand = 0\n')
    p = load_profile(child)
    assert p.data["server"]["ball_rand"] == 0
    assert p.data["server"]["nr_extra_halfs"] == 0


def test_equal_values_equal_hash(tmp_path):
    a = write(tmp_path / "a.toml", '[match]\nhalves = 2\nhalf_time = 300\n[server]\nnr_extra_halfs = 0\n'
              'penalty_shoot_outs = false\n[teams.right]\nteam = "helios"\n[teams.left]\nteam = "helios"\n')
    b = write(tmp_path / "b.toml", 'extends = "default"\n[match]\nhalf_time = 300.0\n')
    assert load_profile(a).hash == load_profile(b).hash == load_profile("default").hash


def test_different_values_different_hash():
    assert load_profile("default").hash != load_profile("short").hash
    assert profile_hash({"x": 1}) != profile_hash({"x": 2})


def test_noise_off_zeroes_every_noise_parameter():
    p = load_profile("noise-off")
    assert all(p.data["server"][k] == 0 for k in NOISE_PARAMS)
    assert all(p.data["player"][k] == 0 for k in PLAYER_NOISE_PARAMS)


def test_short_is_at_most_600_cycles():
    assert load_profile("short").cycles <= 600


def test_unknown_team_is_rejected():
    with pytest.raises(ProfileError, match="unknown team 'cyruss'"):
        load_profile("default", overrides={"teams": {"right": {"team": "cyruss"}}}, known_teams={"helios", "cyrus"})


def test_unknown_section_is_rejected(tmp_path):
    with pytest.raises(ProfileError, match="unknown section.*noise"):
        load_profile(write(tmp_path / "x.toml", 'extends = "default"\n[noise]\nball_rand = 0\n'))


@pytest.mark.parametrize("body, message", [
    ('[server]\nball_rand = [0, 1]\n', "server.ball_rand"),
    ('[server]\nfoo = { a = 1 }\n', "server.foo"),
    ('[server]\nlog = "a b"\n', "server.log"),
    ('[server]\nport = 7000\n', "reserved"),
    ('[server]\nhalf_time = 10\n', "reserved"),
    ('[server]\nconnect_wait = 5\n', "server.connect_wait: this parameter is reserved"),
    ('[teams.right]\nname = "HELIOS_L"\n', "names must differ"),
    ('[teams.left]\nname = "this-name-is-far-too-long"\n', "teams.left.name"),
])
def test_rejects_bad_values(tmp_path, body, message):
    with pytest.raises(ProfileError, match=message):
        load_profile(write(tmp_path / "bad.toml", 'extends = "default"\n' + body))


def test_inheritance_loop(tmp_path):
    write(tmp_path / "a.toml", 'extends = "./b.toml"\n')
    write(tmp_path / "b.toml", 'extends = "./a.toml"\n')
    with pytest.raises(ProfileError, match="loop"):
        load_profile(tmp_path / "a.toml")


def test_swapped_exchanges_teams():
    p = load_profile("default", overrides={"teams": {"right": {"team": "cyrus"}}})
    s = p.swapped()
    assert s.team("left")["team"] == "cyrus" and s.team("right")["team"] == "helios"
    assert isinstance(s, Profile)
