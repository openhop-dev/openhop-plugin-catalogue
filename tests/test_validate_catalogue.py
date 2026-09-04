from __future__ import annotations

import json
import shutil
from email.parser import Parser
from pathlib import Path

import pytest

from scripts.validate_catalogue import (
    CatalogueValidationError,
    _validate_dependencies,
    validate_catalogue,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy_catalogue(tmp_path: Path) -> dict:
    shutil.copytree(ROOT / "schema", tmp_path / "schema")
    shutil.copytree(ROOT / "plugins", tmp_path / "plugins")
    data = json.loads((ROOT / "catalogue.json").read_text(encoding="utf-8"))
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def test_repository_catalogue_and_wheels_validate():
    result = validate_catalogue(ROOT)

    assert result["schema"] == 2
    assert [f"{item['id']}@{item['version']}" for item in result["plugins"]] == [
        "openhop.nomad@0.1.1"
    ]


def test_checksum_mismatch_is_rejected(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["sha256"] = "0" * 64
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CatalogueValidationError, match="sha256 mismatch"):
        validate_catalogue(tmp_path)


def test_non_r2_wheel_url_is_rejected(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["wheel_url"] = "https://example.com/plugin.whl"
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(Exception, match="repeater-plugins"):
        validate_catalogue(tmp_path)


def test_orphan_artifact_is_rejected(tmp_path: Path):
    _copy_catalogue(tmp_path)
    (tmp_path / "plugins" / "unapproved.whl").write_bytes(b"not approved")

    with pytest.raises(CatalogueValidationError, match="unexpected=.*unapproved.whl"):
        validate_catalogue(tmp_path)


def test_wheel_url_query_is_rejected(tmp_path: Path):
    data = _copy_catalogue(tmp_path)
    data["plugins"][0]["wheel_url"] += "?replacement=1"
    (tmp_path / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CatalogueValidationError, match="query"):
        validate_catalogue(tmp_path)


def test_mutable_direct_dependency_is_rejected():
    metadata = Parser().parsestr(
        "Name: sample\nVersion: 1.0.0\n"
        "Requires-Dist: openhop_core @ git+https://github.com/openhop-dev/openhop_core.git@dev\n"
    )

    with pytest.raises(CatalogueValidationError, match="mutable"):
        _validate_dependencies(metadata, Path("sample.whl"))


def test_commit_pinned_direct_dependency_is_allowed():
    metadata = Parser().parsestr(
        "Name: sample\nVersion: 1.0.0\n"
        "Requires-Dist: openhop_core @ git+https://github.com/openhop-dev/openhop_core.git@"
        "8cdb04e734fa836e3847a29c6ec4a3306382150c\n"
    )

    _validate_dependencies(metadata, Path("sample.whl"))


def test_unpinned_registry_dependency_is_rejected():
    metadata = Parser().parsestr(
        "Name: sample\nVersion: 1.0.0\nRequires-Dist: openhop-core>=1.1.1\n"
    )

    with pytest.raises(CatalogueValidationError, match="exact version"):
        _validate_dependencies(metadata, Path("sample.whl"))
