"""Validate the metadata-only openHop plugin catalogue."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import jsonschema
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
APPROVED_DOWNLOAD_ORIGIN = "https://github.com"


class CatalogueValidationError(ValueError):
    """Raised when catalogue approval metadata is inconsistent."""


def _validate_wheel_url(plugin: dict) -> None:
    wheel_url = plugin["wheel_url"]
    parsed = urlparse(wheel_url)
    if f"{parsed.scheme}://{parsed.netloc}" != APPROVED_DOWNLOAD_ORIGIN:
        raise CatalogueValidationError(
            f"wheel_url must use a GitHub Release URL: {wheel_url}"
        )
    if parsed.params or parsed.query or parsed.fragment:
        raise CatalogueValidationError(
            f"wheel_url cannot contain params, query, or fragment: {wheel_url}"
        )

    owner, repository = plugin["repository"].split("/", 1)
    path = Path(unquote(parsed.path))
    parts = path.parts
    expected_prefix = ("/", owner, repository, "releases", "download")
    if len(parts) != 7 or parts[:5] != expected_prefix or parts[5] in {"", ".", ".."}:
        raise CatalogueValidationError(
            f"wheel_url must point to a release asset in {plugin['repository']}"
        )

    filename = parts[6]
    if not filename.endswith(".whl"):
        raise CatalogueValidationError("wheel_url release asset must end in .whl")
    try:
        distribution, version, _build, _tags = parse_wheel_filename(filename)
    except Exception as exc:
        raise CatalogueValidationError(
            f"invalid wheel filename in wheel_url: {filename}"
        ) from exc
    expected_distribution = canonicalize_name(plugin["distribution"])
    if distribution != expected_distribution:
        raise CatalogueValidationError(
            f"wheel filename distribution {distribution} does not match {expected_distribution}"
        )
    if str(version) != plugin["version"]:
        raise CatalogueValidationError(
            f"wheel filename version {version} does not match {plugin['version']}"
        )


def validate_catalogue(root: Path = ROOT) -> dict:
    root = root.resolve()
    catalogue = json.loads((root / "catalogue.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (root / "schema" / "catalogue.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(catalogue)

    ids: set[str] = set()
    repositories: set[str] = set()
    wheel_urls: set[str] = set()
    for plugin in catalogue["plugins"]:
        if plugin["id"] in ids:
            raise CatalogueValidationError(f"duplicate plugin id: {plugin['id']}")
        if plugin["repository"] in repositories:
            raise CatalogueValidationError(
                f"duplicate plugin repository: {plugin['repository']}"
            )
        if plugin["wheel_url"] in wheel_urls:
            raise CatalogueValidationError(
                f"duplicate wheel_url: {plugin['wheel_url']}"
            )
        ids.add(plugin["id"])
        repositories.add(plugin["repository"])
        wheel_urls.add(plugin["wheel_url"])
        _validate_wheel_url(plugin)

    wheels = list(root.rglob("*.whl"))
    if wheels:
        paths = ", ".join(str(path.relative_to(root)) for path in wheels)
        raise CatalogueValidationError(
            f"catalogue repository is metadata-only; remove wheel artifacts: {paths}"
        )
    return catalogue


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
