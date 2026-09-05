# openHop Plugin Catalogue

A small, curated, metadata-only catalogue of approved openHop Repeater plugin releases.

This repository records:

- which plugins are available;
- the single currently approved version of each plugin;
- the immutable plugin source revision;
- the exact GitHub Release wheel URL and SHA-256 digest.

Plugin wheels and plugin source code do not belong in this repository.

## Publishing model

```text
Plugin release/build ──► wheel stored on the plugin's GitHub Release

Reviewed catalogue change
        │
        └── approved version + source revision + GitHub wheel URL + SHA-256
                         │
                         ▼
External catalogue Worker watches main and publishes the catalogue metadata
                         │
                         ▼
https://repeater-plugins.openhop.dev/catalogue.json
                         │
                         ▼
Repeater checks R2 for approved versions, then downloads the selected wheel
straight from the plugin's GitHub Release
```

The external Worker is not a GitHub Action in this repository. GitHub Actions
validate metadata and implement the staged [catalogue-owned publishing policy](docs/publishing-policy.md).

Publishing a plugin release does not by itself approve it. Ordinary catalogue
changes require current maintainer approval. The staged policy allows only narrowly
scoped certified `waev.outpost` updates to qualify without that human review after
an explicit, verified protection cutover. Automatic merging remains disabled until
the activation checklist is completed; existing validation and human review stay in place.

## Catalogue entry format (schema 2)

```json
{
  "schema": 2,
  "plugins": [
    {
      "id": "example.plugin",
      "name": "Example Plugin",
      "description": "Example catalogue entry.",
      "repository": "example-org/example-plugin",
      "category": "integration",
      "logo": "https://example.org/example-plugin.png",
      "distribution": "example-plugin",
      "source_revision": "0123456789abcdef0123456789abcdef01234567",
      "version": "1.2.3",
      "wheel_url": "https://github.com/example-org/example-plugin/releases/download/v1.2.3/example_plugin-1.2.3-py3-none-any.whl",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

The example above is illustrative. Current approvals belong only in
[`catalogue.json`](catalogue.json), so the README does not duplicate live plugin
versions, URLs, or checksums.

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Plugin manifest ID |
| `name` | yes | Display name |
| `description` | yes | Short summary |
| `repository` | yes | Source repository as `owner/repo` |
| `distribution` | yes | Python distribution name used by the wheel |
| `source_revision` | yes | Exact 40-character source commit used to build the wheel |
| `category` | yes | Catalogue grouping and ordering category |
| `logo` | yes | HTTPS URL to the plugin card image |
| `version` | yes | Currently approved plugin version |
| `wheel_url` | yes | Exact wheel asset on the plugin repository's GitHub Release |
| `sha256` | yes | Lowercase SHA-256 digest of the approved published wheel |

## Approval process

1. Build and publish the wheel through the plugin's artifact pipeline.
2. Record the reviewed source commit and calculate the published wheel's SHA-256.
3. Update `catalogue.json` with the approved version, GitHub Release URL, and digest.
4. Open a PR. CI validates:
   - the JSON schema;
   - unique plugin IDs, repositories, and wheel URLs;
   - GitHub Release URL repository and asset layout;
   - URL repository, version, distribution, and wheel filename consistency;
   - checksum and source-revision formatting;
   - that no wheel artifacts were committed to this metadata repository.
5. Merge the approved change to `main`. The external catalogue Worker detects the change and fires.

Repeaters read:

```text
https://repeater-plugins.openhop.dev/catalogue.json
```

## Local validation

```bash
uv run --no-project --isolated --with pytest --with jsonschema \
  --with packaging python -m pytest -q
uv run --no-project --isolated --with jsonschema --with packaging \
  python scripts/validate_catalogue.py
```
