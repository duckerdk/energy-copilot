import hashlib
import json

import pytest

from custom_components.energy_copilot.build_info import read_installed_build
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)


def build_fixture(root):
    (root / "manifest.json").write_text('{"version":"0.1.1"}')
    (root / "__init__.py").write_text("# original payload")
    info = {
        "schema_version": 1,
        "integration": "energy_copilot",
        "version": "0.1.1",
        "tag": "v0.1.1",
        "commit": "a" * 40,
        "source_files_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()
        },
    }
    (root / "BUILD_INFO.json").write_text(json.dumps(info))
    return info


def test_release_identity_from_matching_installed_payload(tmp_path):
    build_fixture(tmp_path)
    result = read_installed_build(tmp_path, "0.1.1")
    assert result == {
        "installed_version": "0.1.1",
        "tag": "v0.1.1",
        "commit": "a" * 40,
        "integrity": "payload_matches_build_info",
    }


@pytest.mark.parametrize("change", ["modified", "missing", "extra", "version"])
def test_changed_payload_never_claims_release_commit(tmp_path, change):
    build_fixture(tmp_path)
    if change == "modified":
        (tmp_path / "__init__.py").write_text("# locally edited")
    elif change == "missing":
        (tmp_path / "__init__.py").unlink()
    elif change == "extra":
        (tmp_path / "extra.py").write_text("# extra payload")
    result = read_installed_build(tmp_path, "0.1.2" if change == "version" else "0.1.1")
    assert result["commit"] is None
    assert result["integrity"] in {"payload_modified", "invalid_metadata"}


def test_bad_metadata_cannot_read_outside_installation(tmp_path):
    info = build_fixture(tmp_path)
    info["source_files_sha256"]["../secret"] = "a" * 64
    (tmp_path / "BUILD_INFO.json").write_text(json.dumps(info))
    assert read_installed_build(tmp_path, "0.1.1")["integrity"] == "invalid_metadata"


async def test_native_diagnostics_identifies_installed_manifest_without_git_head(
    hass, populated_hass, entry
):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["integration_manifest"]["version"] == "1.16.0"
    assert diagnostics["installed_build"]["integrity"] == "metadata_unavailable"
    assert diagnostics["installed_build"]["commit"] is None
    assert (
        hass.states.get("sensor.energy_co_pilot_input_quality").attributes[
            "installed_version"
        ]
        == "1.16.0"
    )
