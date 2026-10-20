#!/usr/bin/env python3
"""Build a reproducible HACS asset from the exact commit of an existing version tag."""

import argparse
import json
import re
import subprocess
import zipfile
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath

COMPONENT = "custom_components/energy_copilot/"
ASSET_NAME = "energy_copilot.zip"
BUILD_INFO = "BUILD_INFO.json"
TAG_PATTERN = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


class ReleaseError(ValueError):
    """A tag, manifest or package failed the release contract."""


def git(repo: Path, *args: str) -> bytes:
    """Read Git objects without depending on the working tree or shell expansion."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True
        ).stdout
    except subprocess.CalledProcessError as err:
        raise ReleaseError(f"Git could not verify release source ({args[0]}).") from err


def source_files(repo: Path, commit: str) -> dict[str, bytes]:
    files = {}
    for item in git(repo, "ls-tree", "-r", "-z", commit, "--", COMPONENT).split(b"\0"):
        if not item:
            continue
        metadata, raw_path = item.split(b"\t", 1)
        mode, kind, object_id = metadata.split()
        path = PurePosixPath(raw_path.decode("utf-8"))
        relative = path.relative_to(COMPONENT.rstrip("/")).as_posix()
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise ReleaseError(
                f"Only regular tracked files may be released: {relative}"
            )
        if (
            relative == BUILD_INFO
            or ".." in path.parts
            or any(part.startswith(".") or part == "__pycache__" for part in path.parts)
            or path.suffix in {".pyc", ".key", ".pem", ".db", ".sqlite", ".log"}
        ):
            raise ReleaseError(
                f"Private/generated files cannot be released: {relative}"
            )
        files[relative] = git(repo, "cat-file", "blob", object_id.decode("ascii"))
    if "manifest.json" not in files or "__init__.py" not in files:
        raise ReleaseError("The tagged commit does not contain a complete integration.")
    return files


def _write_identical_or_new(path: Path, data: bytes) -> None:
    """A rerun may reproduce a file, never silently replace another build."""
    if path.exists() and path.read_bytes() != data:
        raise ReleaseError(
            f"Refusing to replace a different release artifact: {path.name}"
        )
    path.write_bytes(data)


def build_release(repo: Path, tag: str, commit: str, output: Path) -> dict:
    if not TAG_PATTERN.fullmatch(tag):
        raise ReleaseError("Use a stable SemVer tag vX.Y.Z without leading zeros.")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ReleaseError("--commit must be the full lowercase 40-character Git SHA.")
    resolved = (
        git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        .decode()
        .strip()
    )
    if resolved != commit:
        raise ReleaseError(
            "The existing version tag does not identify the requested commit."
        )
    files = source_files(repo, commit)
    try:
        manifest = json.loads(files["manifest.json"])
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise ReleaseError("The tagged manifest is invalid JSON.") from err
    if not isinstance(manifest, dict):
        raise ReleaseError("The tagged manifest must be a JSON object.")
    try:
        hacs = json.loads(git(repo, "show", f"{commit}:hacs.json"))
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise ReleaseError("The tagged HACS configuration is invalid JSON.") from err
    if (
        not isinstance(hacs, dict)
        or hacs.get("zip_release") is not True
        or hacs.get("filename") != ASSET_NAME
    ):
        raise ReleaseError(
            "The tagged HACS configuration does not select this ZIP asset."
        )
    version = tag[1:]
    if manifest.get("version") != version or manifest.get("domain") != "energy_copilot":
        raise ReleaseError("The tag version/domain does not match the tagged manifest.")
    provenance = {
        "schema_version": 1,
        "integration": "energy_copilot",
        "version": version,
        "tag": tag,
        "commit": commit,
        "source_files_sha256": {
            name: sha256(data).hexdigest() for name, data in sorted(files.items())
        },
    }
    info_bytes = (json.dumps(provenance, sort_keys=True, indent=2) + "\n").encode()
    files[BUILD_INFO] = info_bytes
    package = BytesIO()
    with zipfile.ZipFile(
        package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    package_bytes = package.getvalue()
    checksum = f"{sha256(package_bytes).hexdigest()}  {ASSET_NAME}\n".encode()
    output.mkdir(parents=True, exist_ok=True)
    for name, data in (
        (ASSET_NAME, package_bytes),
        ("SHA256SUMS", checksum),
        (BUILD_INFO, info_bytes),
    ):
        _write_identical_or_new(output / name, data)
    return {
        "version": version,
        "tag": tag,
        "commit": commit,
        "asset": str(output / ASSET_NAME),
        "sha256": sha256(package_bytes).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_release(args.repo, args.tag, args.commit, args.output)
    except ReleaseError as err:
        parser.exit(1, f"Release validation failed: {err}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
