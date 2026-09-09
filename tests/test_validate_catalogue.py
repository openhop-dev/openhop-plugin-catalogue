from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import pytest
from scripts.validate_catalogue import CatalogueValidationError, validate_catalogue

ROOT = Path(__file__).resolve().parents[1]


def _copy_catalogue(tmp_path: Path) -> dict:
    shutil.copytree(ROOT / "schema", tmp_path / "schema")
    data = json.loads((ROOT / "catalogue.json").read_text(encoding="utf-8"))
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def test_repository_catalogue_metadata_validates():
    result = validate_catalogue(ROOT)

    assert result["schema"] == 2
    plugins = {item["id"]: item for item in result["plugins"]}
    assert plugins["openhop.nomad"]["version"] == "0.1.2"
    assert plugins["openhop.nomad"]["category"] == "integration"
    assert plugins["openhop.nomad"]["logo"] == (
        "https://cdn.jsdelivr.net/gh/selfhst/icons/png/project-nomad.png"
    )


@pytest.mark.parametrize("field", ["category", "logo"])
def test_display_metadata_is_required(tmp_path: Path, field: str):
    data = _copy_catalogue(tmp_path)
    del data["plugins"][0][field]
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(jsonschema.ValidationError, match="required"):
        validate_catalogue(tmp_path)


def test_repository_contains_no_wheel_artifacts():
    assert list(ROOT.rglob("*.whl")) == []


def test_non_github_release_wheel_url_is_rejected(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["wheel_url"] = "https://example.com/plugin.whl"
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(jsonschema.ValidationError, match="github"):
        validate_catalogue(tmp_path)


def test_wheel_url_query_is_rejected(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["wheel_url"] += "?replacement=1"
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CatalogueValidationError, match="query"):
        validate_catalogue(tmp_path)


def test_wheel_url_repository_must_match_catalogue_repository(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["wheel_url"] = data["plugins"][0]["wheel_url"].replace(
        "openhop-dev/openhop-nomad-plugin", "someone-else/other-plugin"
    )
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CatalogueValidationError, match="release asset"):
        validate_catalogue(tmp_path)


def test_wheel_filename_version_must_match_approved_version(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["wheel_url"] = data["plugins"][0]["wheel_url"].replace(
        "openhop_nomad_plugin-0.1.2", "openhop_nomad_plugin-9.9.9"
    )
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CatalogueValidationError, match="filename version"):
        validate_catalogue(tmp_path)


def test_wheel_filename_distribution_must_match(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["wheel_url"] = data["plugins"][0]["wheel_url"].replace(
        "openhop_nomad_plugin", "other_plugin"
    )
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CatalogueValidationError, match="distribution"):
        validate_catalogue(tmp_path)


def test_invalid_checksum_format_is_rejected(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["sha256"] = "not-a-checksum"
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(jsonschema.ValidationError, match="does not match"):
        validate_catalogue(tmp_path)


def test_wheel_artifact_in_repository_is_rejected(tmp_path: Path):
    _copy_catalogue(tmp_path)
    (tmp_path / "accidental.whl").write_bytes(b"do not commit plugin artifacts")

    with pytest.raises(CatalogueValidationError, match="metadata-only"):
        validate_catalogue(tmp_path)
