# openHop Plugin Catalogue

A small, curated, metadata-only catalogue of approved openHop Repeater plugin releases.

This repository records:

- which plugins are available;
- the single currently approved version of each plugin;
- the immutable plugin source revision;
- the exact R2 wheel URL and SHA-256 digest.

Plugin wheels and plugin source code do not belong in this repository.

## Publishing model

```text
Plugin release/build
        │
        └── wheel published by the plugin artifact pipeline

Reviewed catalogue change
        │
        └── version + source revision + R2 URL + SHA-256
                         │
                         ▼
External catalogue Worker watches main and reacts to the change
                         │
                         ▼
https://repeater-plugins.openhop.dev/catalogue.json
```

The external Worker is not a GitHub Action in this repository. GitHub Actions here only validates catalogue metadata.

Publishing a plugin release does not automatically approve it. Approval requires a reviewed catalogue change naming the exact version, source revision, destination URL, and digest.

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
      "distribution": "example-plugin",
      "source_revision": "0123456789abcdef0123456789abcdef01234567",
      "version": "1.2.3",
      "wheel_url": "https://repeater-plugins.openhop.dev/plugins/example.plugin/1.2.3/example_plugin-1.2.3-py3-none-any.whl",
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
| `category` | no | Free-form catalogue category |
| `logo` | no | HTTPS URL to a catalogue icon |
| `version` | yes | Currently approved plugin version |
| `wheel_url` | yes | Exact destination under the approved R2 origin and version path |
| `sha256` | yes | Lowercase SHA-256 digest of the approved published wheel |

## Approval process

1. Build and publish the wheel through the plugin's artifact pipeline.
2. Record the reviewed source commit and calculate the published wheel's SHA-256.
3. Update `catalogue.json` with the approved version, R2 URL, and digest.
4. Open a PR. CI validates:
   - the JSON schema;
   - unique plugin IDs, repositories, and wheel URLs;
   - R2-only URL layout;
   - URL plugin ID, version, distribution, and wheel filename consistency;
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
