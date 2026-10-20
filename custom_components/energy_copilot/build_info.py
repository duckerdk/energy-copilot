"""Identify the installed payload from release metadata, never the checkout HEAD."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from homeassistant.loader import async_get_integration

from .const import DOMAIN


def read_installed_build(root: Path, installed_version: str) -> dict:
    result = {
        "installed_version": installed_version,
        "tag": None,
        "commit": None,
        "integrity": "metadata_unavailable",
    }
    try:
        info = json.loads((root / "BUILD_INFO.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return result
    except OSError, ValueError:
        return {**result, "integrity": "invalid_metadata"}
    try:
        if (
            info["schema_version"] != 1
            or info["integration"] != DOMAIN
            or info["version"] != installed_version
            or info["tag"] != f"v{installed_version}"
            or not re.fullmatch(r"[0-9a-f]{40}", info["commit"])
        ):
            raise ValueError("invalid_build_identity")
        hashes = info["source_files_sha256"]
        if not isinstance(hashes, dict) or "manifest.json" not in hashes:
            raise ValueError("invalid_hash_manifest")
        actual_files = {
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix not in {".pyc", ".pyo"}
            and p.name != "BUILD_INFO.json"
        }
        modified = actual_files != set(hashes)
        for name, expected in hashes.items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("invalid_build_path")
            target = root.joinpath(*path.parts).resolve()
            if not target.is_relative_to(root.resolve()) or not re.fullmatch(
                r"[0-9a-f]{64}", expected
            ):
                raise ValueError("invalid_build_hash")
            try:
                modified |= hashlib.sha256(target.read_bytes()).hexdigest() != expected
            except OSError:
                modified = True
        if modified:
            return {
                **result,
                "integrity": "payload_modified",
                "declared_tag": info["tag"],
                "declared_commit": info["commit"],
            }
        return {
            **result,
            "tag": info["tag"],
            "commit": info["commit"],
            "integrity": "payload_matches_build_info",
        }
    except KeyError, TypeError, ValueError, OSError:
        return {**result, "integrity": "invalid_metadata"}


async def async_installed_build(hass):
    integration = await async_get_integration(hass, DOMAIN)
    return await hass.async_add_executor_job(
        read_installed_build, Path(__file__).parent, integration.manifest["version"]
    )
