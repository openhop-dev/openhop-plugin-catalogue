# openHop Plugin Catalogue

A small, curated catalogue of approved openHop Repeater plugin releases.

The repository is the source of truth for:

- which plugins are available;
- the single currently approved version of each plugin;
- the immutable source revision, exact R2 wheel URL, and SHA-256 digest;
- the wheel artifact published to the R2-backed plugin origin.

## Design

```text
Catalogue PR and review
        │
        ├── catalogue.json approves source revision, version, URL, and SHA-256
        └── plugins/.../*.whl contains the exact approved artifact
                         │
                         ▼
https://repeater-plugins.openhop.dev
                         │
                         ▼
openHop Plugin Manager verifies SHA-256, installs, enables, and runs
```

Publishing a GitHub Release does not automatically approve a plugin update.
Approval requires a reviewed catalogue change containing the exact wheel and
matching checksum. This keeps version promotion under openHop's control and
removes the Repeater's dependency on GitHub API rate limits.

## Catalogue entry format (schema 2)

```json
{
  "schema": 2,
  "plugins": [
    {
      "id": "openhop.nomad",
      "name": "NOMAD Bridge",
      "description": "Connects an openHop Companion identity to Project N.O.M.A.D.",
      "repository": "openhop-dev/openhop-nomad-plugin",
      "distribution": "openhop-nomad-plugin",
      "source_revision": "4b061aa0bd975ad8e90cf32ced94ccb5599f96d0",
      "version": "0.1.1",
      "wheel_url": "https://repeater-plugins.openhop.dev/plugins/openhop.nomad/0.1.1/openhop_nomad_plugin-0.1.1-py3-none-any.whl",
      "sha256": "6576a9d737cfefd11e17cd982a8a3d3ccffdbff342b489dcea95d8670b0ca9e7"
    }
  ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Must match the wheel's `openhop-plugin.json` `id` |
| `name` | yes | Display name |
| `description` | yes | Short summary |
| `repository` | yes | Source repository as `owner/repo` |
| `distribution` | yes | Python distribution name in the wheel filename and `METADATA` |
| `source_revision` | yes | Exact 40-character source commit used to build the wheel |
| `category` | no | Free-form label such as `integration` |
| `logo` | no | HTTPS URL to a catalogue icon |
| `version` | yes | Currently approved plugin version |
| `wheel_url` | yes | Exact wheel under the approved R2 origin and version path |
| `sha256` | yes | Lowercase SHA-256 digest of the approved wheel |

## Artifact layout

```text
plugins/
└── openhop.nomad/
    └── 0.1.1/
        └── openhop_nomad_plugin-0.1.1-py3-none-any.whl
```

The public URL mirrors that repository path:

```text
https://repeater-plugins.openhop.dev/plugins/openhop.nomad/0.1.1/openhop_nomad_plugin-0.1.1-py3-none-any.whl
```

## Approving a plugin version

1. Obtain the wheel from the exact reviewed `source_revision`.
2. Inspect its embedded `openhop-plugin.json`.
3. Add the wheel under `plugins/<id>/<version>/`.
4. Set the matching `distribution`, `source_revision`, `version`, `wheel_url`,
   and `sha256` in `catalogue.json`.
5. Open a PR. CI validates:
   - JSON schema;
   - unique plugin IDs and exact equality between catalogue artifacts and
     everything publishable under `plugins/`;
   - R2-only URL layout;
   - local artifact presence;
   - SHA-256 equality;
   - wheel filename, `METADATA`, `RECORD`, and embedded manifest identity;
   - runtime dependencies use exact package versions or immutable VCS commits.
6. Merge the approved change to `main`. The external catalogue Worker watches
   the repository and publishes the allowed assets to R2; no deployment GitHub
   Action is involved.

Repeaters read the catalogue from:

```text
https://repeater-plugins.openhop.dev/catalogue.json
```

## Local validation

```bash
uv run --no-project --isolated --with pytest --with jsonschema \
  --with packaging --with wheel \
  python -m pytest -q
uv run --no-project --isolated --with jsonschema --with packaging --with wheel \
  python scripts/validate_catalogue.py
```

Or install `pytest`, `jsonschema`, `packaging`, and `wheel` in a virtual
environment and run the same Python commands directly.
