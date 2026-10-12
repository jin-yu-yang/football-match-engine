from pathlib import Path

from matchlab import paths


def test_repo_root_contains_pins():
    root = paths.repo_root()
    assert (root / "testbed" / "pins.toml").is_file()


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MATCHLAB_ROOT", str(tmp_path))
    assert paths.repo_root() == tmp_path.resolve()
    assert paths.work_dir() == tmp_path.resolve() / ".testbed"
    assert paths.manifest_path() == tmp_path.resolve() / ".testbed" / "manifest.json"
    assert paths.profiles_dir() == tmp_path.resolve() / "testbed" / "profiles"
