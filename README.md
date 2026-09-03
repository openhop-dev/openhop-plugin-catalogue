# openHop Plugin Catalogue

A **small, curated, static catalogue** of openHop Repeater plugins.

The catalogue tells a Repeater:

- which plugins exist
- display name / description / category
- which GitHub repository publishes them

It does **not** store versions, download URLs, or release assets.

## Design

```text
openHop Plugin Catalogue  →  repository metadata only
        │
        ▼
GitHub Releases           →  versions, wheels, release notes
        │
        ▼
openHop Plugin Manager    →  install / enable / run / update
```

> **Updating a plugin does not require changing this catalogue.**  
> Publish a new GitHub Release on the plugin repository instead.

## Catalogue entry format (schema 1)

```json
{
  "schema": 1,
  "plugins": [
    {
      "id": "openhop.nomad",
      "name": "NOMAD Bridge",
      "description": "Connects an openHop Companion identity to Project N.O.M.A.D.",
      "repository": "openhop-dev/openhop-nomad-plugin",
      "category": "integration"
    }
  ]
}
```

| Field | Required | Notes |
|-------|----------|--------|
| `id` | yes | Must match the plugin's `openhop-plugin.json` `id` |
| `name` | yes | Display name |
| `description` | yes | Short summary |
| `repository` | yes | `owner/repo` (not a full URL) |
| `category` | no | Free-form label (e.g. `integration`) |

Do **not** put `latest_version`, download URLs, or wheel filenames here.

## Plugin requirements

1. Ship an `openhop-plugin.json` manifest (schema 1) whose `id` matches the catalogue entry.
2. Publish **GitHub Releases** with tags like `v1.2.3`.
3. Attach exactly one installable `*.whl` asset per stable release (draft/prerelease ignored by default).

## How to submit a plugin

1. Build and publish your openHop plugin with GitHub Releases + a wheel asset.
2. Open a PR against this repository adding one object to `catalogue.json`.
3. CI validates JSON schema, unique IDs, and unique repositories (no network calls).
4. After merge, Repeaters discover the plugin from:

   `https://raw.githubusercontent.com/openhop-dev/openhop-plugin-catalogue/main/catalogue.json`

## What this is not

- Not a package registry or backend service
- Not a marketplace (no ratings, payments, or auto-approval)
- Not the version source — **GitHub Releases are**

## Local validation

```bash
pip install 'jsonschema>=4.0'
python -c "import json; from jsonschema import Draft202012Validator; \
  d=json.load(open('catalogue.json')); s=json.load(open('schema/catalogue.schema.json')); \
  Draft202012Validator(s).validate(d); print('OK')"
```
