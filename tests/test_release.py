"""Release assets identify the tagged source, never local dirt or an arbitrary HEAD."""

import json
import subprocess
import zipfile
from hashlib import sha256

import pytest

from scripts.build_release import ASSET_NAME, BUILD_INFO, ReleaseError, build_release


def command(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo, message="source"):
    command(repo, "add", ".")
    command(
        repo,
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release@example.invalid",
        "commit",
        "-m",
        message,
    )
    return command(repo, "rev-parse", "HEAD")


@pytest.fixture
def tagged_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    command(repo, "init")
    component = repo / "custom_components" / "energy_copilot"
    (component / "translations").mkdir(parents=True)
    (component / "manifest.json").write_text(
        json.dumps({"domain": "energy_copilot", "version": "0.1.1"})
    )
    (component / "__init__.py").write_text('"""Read-only test integration."""\n')
    (component / "translations" / "en.json").write_text('{"title":"Energy Co-Pilot"}\n')
    (repo / "hacs.json").write_text(
        json.dumps({"zip_release": True, "filename": ASSET_NAME})
    )
    revision = commit(repo)
    command(repo, "tag", "v0.1.1")
    return repo, component, revision


def test_release_root_layout_provenance_hashes_and_dirty_tree_isolation(
    tagged_repo, tmp_path
):
    repo, component, revision = tagged_repo
    (component / "__init__.py").write_text("LOCAL_UNCOMMITTED_EDIT\n")
    (component / ".env").write_text("PRIVATE_LOCAL_VALUE\n")
    (component / "manifest.json").write_text('{"version":"99.0.0"}')
    output = tmp_path / "release"
    result = build_release(repo, "v0.1.1", revision, output)
    assert result["commit"] == revision
    with zipfile.ZipFile(output / ASSET_NAME) as archive:
        assert sorted(archive.namelist()) == [
            BUILD_INFO,
            "__init__.py",
            "manifest.json",
            "translations/en.json",
        ]
        assert b"LOCAL_UNCOMMITTED_EDIT" not in archive.read("__init__.py")
        assert json.loads(archive.read("manifest.json"))["version"] == "0.1.1"
        info = json.loads(archive.read(BUILD_INFO))
        assert info["version"] == "0.1.1"
        assert info["tag"] == "v0.1.1"
        assert info["commit"] == revision
        assert info["integration"] == "energy_copilot"
        assert info["schema_version"] == 1
        for name, expected in info["source_files_sha256"].items():
            assert sha256(archive.read(name)).hexdigest() == expected
        assert BUILD_INFO not in info["source_files_sha256"]
        assert (output / BUILD_INFO).read_bytes() == archive.read(BUILD_INFO)
    expected_checksum = sha256((output / ASSET_NAME).read_bytes()).hexdigest()
    assert (output / "SHA256SUMS").read_text() == f"{expected_checksum}  {ASSET_NAME}\n"


def test_same_tag_is_reproducible_and_local_rebuild_is_idempotent(
    tagged_repo, tmp_path
):
    repo, _, revision = tagged_repo
    first, second = tmp_path / "first", tmp_path / "second"
    build_release(repo, "v0.1.1", revision, first)
    build_release(repo, "v0.1.1", revision, second)
    build_release(repo, "v0.1.1", revision, first)
    for name in (ASSET_NAME, BUILD_INFO, "SHA256SUMS"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_tag_must_match_manifest_in_exact_tagged_commit(tagged_repo, tmp_path):
    repo, _, revision = tagged_repo
    command(repo, "tag", "v0.1.2")
    with pytest.raises(ReleaseError, match="does not match"):
        build_release(repo, "v0.1.2", revision, tmp_path / "release")


def test_requested_commit_cannot_substitute_for_the_tag(tagged_repo, tmp_path):
    repo, component, _ = tagged_repo
    (component / "__init__.py").write_text("LATER_COMMIT\n")
    later = commit(repo, "later")
    with pytest.raises(ReleaseError, match="does not identify"):
        build_release(repo, "v0.1.1", later, tmp_path / "release")


@pytest.mark.parametrize(
    "tag,revision",
    [
        ("v01.1.1", "a" * 40),
        ("v0.1.1;bad", "a" * 40),
        ("v0.1.1", "HEAD"),
        ("v0.1.1", "abc"),
    ],
)
def test_invalid_tag_or_short_sha_rejected(tagged_repo, tmp_path, tag, revision):
    repo, _, _ = tagged_repo
    with pytest.raises(ReleaseError):
        build_release(repo, tag, revision, tmp_path / "release")


def test_missing_tag_cannot_be_invented_by_builder(tagged_repo, tmp_path):
    repo, _, revision = tagged_repo
    with pytest.raises(ReleaseError, match="Git could not verify"):
        build_release(repo, "v0.1.2", revision, tmp_path / "release")


def test_symlinks_are_not_followed_into_release(tagged_repo, tmp_path):
    repo, component, _ = tagged_repo
    target = tmp_path / "private.py"
    target.write_text("PRIVATE\n")
    (component / "linked.py").symlink_to(target)
    revision = commit(repo, "symlink")
    command(repo, "tag", "-d", "v0.1.1")
    command(repo, "tag", "v0.1.1")
    with pytest.raises(ReleaseError, match="regular tracked"):
        build_release(repo, "v0.1.1", revision, tmp_path / "release")


def test_tracked_generated_build_info_cannot_spoof_provenance(tagged_repo, tmp_path):
    repo, component, _ = tagged_repo
    (component / BUILD_INFO).write_text('{"commit":"fake"}')
    revision = commit(repo, "spoof")
    command(repo, "tag", "v0.1.2")
    with pytest.raises(ReleaseError, match="Private/generated"):
        build_release(repo, "v0.1.2", revision, tmp_path / "release")


def test_different_existing_output_is_never_silently_replaced(tagged_repo, tmp_path):
    repo, _, revision = tagged_repo
    output = tmp_path / "release"
    output.mkdir()
    (output / ASSET_NAME).write_bytes(b"ANOTHER_BUILD")
    with pytest.raises(ReleaseError, match="Refusing to replace"):
        build_release(repo, "v0.1.1", revision, output)
    assert (output / ASSET_NAME).read_bytes() == b"ANOTHER_BUILD"


def test_tagged_hacs_config_must_select_the_release_zip(tagged_repo, tmp_path):
    repo, _, _ = tagged_repo
    (repo / "hacs.json").write_text(
        json.dumps({"zip_release": True, "filename": "wrong.zip"})
    )
    revision = commit(repo, "wrong asset")
    command(repo, "tag", "v0.1.2")
    with pytest.raises(ReleaseError, match="does not select"):
        build_release(repo, "v0.1.2", revision, tmp_path / "release")
