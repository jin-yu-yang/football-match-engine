import subprocess

import pytest

from matchlab.patches import PatchError, apply_patches, list_patches, patch_checksum


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


def make_repo(path):
    path.mkdir()
    git(path, "init", "-q")
    (path / "a.txt").write_text("one\n")
    git(path, "add", "a.txt")
    git(path, "commit", "-q", "-m", "init")
    return path


def diff_for(repo, new_text):
    (repo / "a.txt").write_text(new_text)
    out = subprocess.run(["git", "diff"], cwd=repo, check=True, capture_output=True, text=True).stdout
    git(repo, "checkout", "--", "a.txt")
    return out


def write_patch(folder, name, group, body):
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(f"Group: {group}\nReason: test\n\n{body}")
    return path


def test_lists_in_numeric_order_and_applies(tmp_path):
    repo = make_repo(tmp_path / "src")
    first = diff_for(repo, "one\ntwo\n")
    (repo / "a.txt").write_text("one\ntwo\n")
    git(repo, "commit", "-q", "-am", "two")
    second = diff_for(repo, "one\ntwo\nthree\n")  # relative to the state after the first patch
    git(repo, "reset", "-q", "--hard", "HEAD~1")
    folder = tmp_path / "patches"
    write_patch(folder, "0002-add-three.patch", "seed", second)
    write_patch(folder, "0001-add-two.patch", "build-fix", first)

    patches = list_patches(folder)
    assert [p.number for p in patches] == [1, 2]
    assert [p.group for p in patches] == ["build-fix", "seed"]

    apply_patches(repo, "demo", patches)
    assert (repo / "a.txt").read_text() == "one\ntwo\nthree\n"
    assert len(patch_checksum(patches[0])) == 64


def test_failure_names_component_and_patch(tmp_path):
    repo = make_repo(tmp_path / "src")
    body = diff_for(repo, "changed\n").replace("-one", "-not-there")
    folder = tmp_path / "patches"
    write_patch(folder, "0001-broken.patch", "build-fix", body)
    with pytest.raises(PatchError, match=r"demo: patch 0001-broken.patch does not apply"):
        apply_patches(repo, "demo", list_patches(folder))


def test_missing_folder_means_no_patches(tmp_path):
    assert list_patches(tmp_path / "none") == []


def test_rejects_bad_name_and_header(tmp_path):
    folder = tmp_path / "patches"
    write_patch(folder, "fix.patch", "build-fix", "")
    with pytest.raises(PatchError, match="NNNN-name.patch"):
        list_patches(folder)
    (folder / "fix.patch").unlink()
    (folder / "0001-x.patch").write_text("Reason: no group\n\ndiff --git a/a b/a\n")
    with pytest.raises(PatchError, match="Group"):
        list_patches(folder)
