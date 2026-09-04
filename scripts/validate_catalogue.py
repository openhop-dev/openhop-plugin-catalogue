"""Validate catalogue metadata and its approved local wheel artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import unquote, urlparse

import jsonschema
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename
from wheel.wheelfile import WheelError, WheelFile

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_PATH = ROOT / "catalogue.json"
SCHEMA_PATH = ROOT / "schema" / "catalogue.schema.json"
ARTIFACT_ROOT = ROOT / "plugins"
APPROVED_ORIGIN = "https://repeater-plugins.openhop.dev"
PINNED_GIT_URL_RE = re.compile(r"^git\+https://[^@\s]+@[0-9a-f]{40}$")


class CatalogueValidationError(ValueError):
    """Raised when approval metadata and repository artifacts disagree."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(wheel_url: str) -> Path:
    parsed = urlparse(wheel_url)
    if f"{parsed.scheme}://{parsed.netloc}" != APPROVED_ORIGIN:
        raise CatalogueValidationError(
            f"wheel_url must use the approved R2 origin {APPROVED_ORIGIN}: {wheel_url}"
        )
    if parsed.params or parsed.query or parsed.fragment:
        raise CatalogueValidationError(
            f"wheel_url cannot contain params, query, or fragment: {wheel_url}"
        )

    relative = Path(unquote(parsed.path).lstrip("/"))
    candidate = (ROOT / relative).resolve()
    try:
        candidate.relative_to(ARTIFACT_ROOT.resolve())
    except ValueError as exc:
        raise CatalogueValidationError(
            f"wheel_url escapes plugins/: {wheel_url}"
        ) from exc
    if candidate.suffix != ".whl":
        raise CatalogueValidationError(f"approved artifact must be a .whl: {candidate}")
    return candidate


def _validate_dependencies(metadata, artifact: Path) -> None:
    for raw in metadata.get_all("Requires-Dist", []):
        try:
            requirement = Requirement(raw)
        except InvalidRequirement as exc:
            raise CatalogueValidationError(
                f"invalid Requires-Dist in {artifact.name}: {raw}"
            ) from exc
        if requirement.marker and "extra" in str(requirement.marker):
            continue
        if requirement.url and not PINNED_GIT_URL_RE.fullmatch(requirement.url):
            raise CatalogueValidationError(
                f"mutable or unapproved direct dependency in {artifact.name}: {raw}"
            )
        if not requirement.url:
            specifiers = list(requirement.specifier)
            if (
                len(specifiers) != 1
                or specifiers[0].operator != "=="
                or "*" in specifiers[0].version
            ):
                raise CatalogueValidationError(
                    f"runtime dependency must use one exact version in {artifact.name}: {raw}"
                )


def _validate_wheel(plugin: dict, artifact: Path) -> None:
    try:
        filename_name, filename_version, _build, _tags = parse_wheel_filename(
            artifact.name
        )
    except Exception as exc:
        raise CatalogueValidationError(
            f"invalid wheel filename: {artifact.name}"
        ) from exc

    expected_distribution = canonicalize_name(plugin["distribution"])
    if filename_name != expected_distribution:
        raise CatalogueValidationError(
            f"wheel distribution {filename_name} does not match {expected_distribution}"
        )
    if str(filename_version) != plugin["version"]:
        raise CatalogueValidationError(
            f"wheel filename version {filename_version} does not match {plugin['version']}"
        )

    try:
        with WheelFile(artifact) as wheel:
            names = wheel.namelist()
            metadata_names = [
                name for name in names if name.endswith(".dist-info/METADATA")
            ]
            wheel_files = [name for name in names if name.endswith(".dist-info/WHEEL")]
            record_files = [
                name for name in names if name.endswith(".dist-info/RECORD")
            ]
            manifest_names = [
                name
                for name in names
                if name.endswith("/openhop-plugin.json")
                or name == "openhop-plugin.json"
            ]
            if (
                len(metadata_names) != 1
                or len(wheel_files) != 1
                or len(record_files) != 1
            ):
                raise CatalogueValidationError(
                    f"wheel must contain exactly one METADATA, WHEEL, and RECORD: {artifact.name}"
                )
            if len(manifest_names) != 1:
                raise CatalogueValidationError(
                    f"wheel must contain exactly one openhop-plugin.json: {artifact.name}"
                )

            # WheelFile verifies every RECORD hash as each member is read.
            for name in names:
                wheel.read(name)

            metadata = BytesParser(policy=default).parsebytes(
                wheel.read(metadata_names[0])
            )
            manifest = json.loads(wheel.read(manifest_names[0]))
    except CatalogueValidationError:
        raise
    except (WheelError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        raise CatalogueValidationError(f"invalid wheel {artifact}: {exc}") from exc

    if canonicalize_name(metadata["Name"] or "") != expected_distribution:
        raise CatalogueValidationError(
            f"wheel metadata Name {metadata['Name']!r} does not match {plugin['distribution']!r}"
        )
    if metadata["Version"] != plugin["version"]:
        raise CatalogueValidationError(
            f"wheel metadata Version {metadata['Version']!r} does not match {plugin['version']!r}"
        )
    if manifest.get("id") != plugin["id"]:
        raise CatalogueValidationError(
            f"wheel manifest id {manifest.get('id')!r} does not match {plugin['id']!r}"
        )
    if manifest.get("version") != plugin["version"]:
        raise CatalogueValidationError(
            f"wheel manifest version {manifest.get('version')!r} does not match "
            f"{plugin['version']!r}"
        )
    _validate_dependencies(metadata, artifact)


def _repository_artifacts() -> set[Path]:
    if not ARTIFACT_ROOT.exists():
        return set()
    artifacts: set[Path] = set()
    for path in ARTIFACT_ROOT.rglob("*"):
        if path.is_symlink():
            raise CatalogueValidationError(
                f"symlinks are not allowed under plugins/: {path}"
            )
        if path.is_file():
            artifacts.add(path.resolve())
    return artifacts


def validate_catalogue(root: Path = ROOT) -> dict:
    global ROOT, CATALOGUE_PATH, SCHEMA_PATH, ARTIFACT_ROOT
    previous = (ROOT, CATALOGUE_PATH, SCHEMA_PATH, ARTIFACT_ROOT)
    ROOT = root.resolve()
    CATALOGUE_PATH = ROOT / "catalogue.json"
    SCHEMA_PATH = ROOT / "schema" / "catalogue.schema.json"
    ARTIFACT_ROOT = ROOT / "plugins"
    try:
        catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(catalogue)

        ids: set[str] = set()
        expected_artifacts: set[Path] = set()
        for plugin in catalogue["plugins"]:
            if plugin["id"] in ids:
                raise CatalogueValidationError(f"duplicate plugin id: {plugin['id']}")
            ids.add(plugin["id"])

            artifact = _artifact_path(plugin["wheel_url"])
            if artifact in expected_artifacts:
                raise CatalogueValidationError(
                    f"artifact referenced more than once: {artifact}"
                )
            expected_artifacts.add(artifact)
            if artifact.is_symlink():
                raise CatalogueValidationError(
                    f"approved artifact cannot be a symlink: {artifact}"
                )
            if not artifact.is_file():
                raise CatalogueValidationError(f"approved wheel is missing: {artifact}")
            actual_hash = _sha256(artifact)
            if actual_hash != plugin["sha256"]:
                raise CatalogueValidationError(
                    f"sha256 mismatch for {artifact}: expected {plugin['sha256']}, got {actual_hash}"
                )
            _validate_wheel(plugin, artifact)

        actual_artifacts = _repository_artifacts()
        if actual_artifacts != expected_artifacts:
            unexpected = sorted(
                str(path.relative_to(ROOT))
                for path in actual_artifacts - expected_artifacts
            )
            missing = sorted(
                str(path.relative_to(ROOT))
                for path in expected_artifacts - actual_artifacts
            )
            raise CatalogueValidationError(
                f"plugins/ must exactly match catalogue artifacts; unexpected={unexpected}, missing={missing}"
            )
        return catalogue
    finally:
        ROOT, CATALOGUE_PATH, SCHEMA_PATH, ARTIFACT_ROOT = previous


def main() -> int:
    try:
        catalogue = validate_catalogue()
    except (
        CatalogueValidationError,
        jsonschema.ValidationError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    approved = ", ".join(
        f"{item['id']}@{item['version']}" for item in catalogue["plugins"]
    )
    print(f"OK: {len(catalogue['plugins'])} approved plugin(s): {approved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
