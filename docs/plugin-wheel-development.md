# Build a Repeater plugin wheel

This guide is for developers building an external app for openHop Repeater. You
can upload a wheel to your own test installation **without a catalogue listing or
PR**. For public inclusion, follow [Adding a third-party app](third-party-apps.md)
after testing. Keep your app's source and wheels in its own repository, not here.

**Source baseline:** public `openhop-dev/openhop_repeater` remote `main` at
[`13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b`](https://github.com/openhop-dev/openhop_repeater/tree/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b).
The contracts below come from that revision's parser, installer, manager and web
handlers—not from another app's packaging or this catalogue's certification
profiles. Check your installed Repeater version before relying on this baseline.
The embedded manifest is **schema 1**; catalogue metadata is independently schema 2.

## Choose the app shape

Repeater manages external applications rather than importing an extension into
its daemon. Apps can use existing REST, WebSocket/SSE or Companion interfaces;
there is no in-process plugin SDK or automatic radio/API credential injection.

- **Service:** `runtime.type: "python"` and a bare console-script name. This is the
  only supported runtime type. Use a foreground, long-running process.
- **Application UI:** `ui.type: "application"` and an entry such as `ui/index.html`.
  A UI-only wheel is extracted without creating a Python venv or running pip.
- **Hybrid:** declare both. Other runtime types and dashboard-widget UI types are
  not supported by this parser.

Source: [manifest validation][manifest], [installation and process startup][runtime],
[upstream plugin overview][overview].

## Wheel and manifest contract

Supply a real `.whl`, not a source archive or a ZIP renamed to `.whl`. Python
services must be pip-installable on the target Python/OS/architecture. The manager
uses its own Python executable to create a separate venv for each release; it
does not select a Python version from the manifest. Use appropriate wheel tags,
`requires-python` and dependency metadata. A `py3-none-any` wheel is suitable for
the pure-Python example below, not a promise that native binaries are portable.

The wheel reader finds files named `openhop-plugin.json` at the archive root or
at any nested path. It prefers a candidate containing `share/openhop/plugins/`,
otherwise takes the first candidate. Use **one unambiguous manifest** at the
standard data-files location:

```text
<distribution>-<version>.data/data/share/openhop/plugins/<plugin-id>/openhop-plugin.json
```

Setuptools generates that wheel path from the `data-files` configuration below.
A duplicate root manifest, particular Python package name, or catalogue profile
is **not** a universal Repeater requirement. Discovery alone does not prove that
a wheel installs or its console script exists.

| Manifest field | Contract at this baseline |
| --- | --- |
| `schema` | Use JSON integer `1`. |
| `id` | Required nonempty string, at most 128 characters; lowercase letters/digits plus `.`, `_`, `-`; first character a letter/digit; no `..` or path separators. Keep stable across releases. |
| `name` | Required nonempty display-name string. |
| `version` | Required semantic-version-shaped string: three numeric components with no leading zeros, optionally followed by `-` or `+` and letters/digits/dots/hyphens. Use `1.0.0` to avoid differences from Python version normalization. |
| `description` | Optional string; missing or null becomes empty. |
| `runtime` | Optional object: `type: "python"`, `entrypoint` a bare console-script name, not `module:callable`, a file path, or a shell command. Allowed name characters are letters/digits and `.`, `_`, `+`, `-`, starting with a letter/digit. |
| `ui` | Optional object: `type: "application"`, `entry` a relative path inside a dedicated public subtree. |
| `config` | Optional object with optional `defaults` JSON object, serialized size at most 256 KiB. No plugin-specific setting validation is supplied. |

At least one of `runtime` or `ui` must be present. Unknown keys are not an
extension mechanism: the parser constructs only the fields above. The local
parser does not cross-check distribution metadata against manifest identity and
version; keep them consistent for release tooling and catalogue review anyway.

Archive checks bound expanded content to 4,096 members, 16 MiB per member and
256 MiB total; manifest/default-file metadata reads are limited to 1 MiB. IPC
staging accepts regular wheel files up to 100 MiB. These are distinct checks,
not a guarantee that every HTTP upload is rejected before being written to disk.
Sources: [manifest/discovery/limits][manifest], [local staging][manager],
[HTTP upload handler][api].

## Minimal Python service: build these three files

Create a new project directory **outside the catalogue checkout**:

```text
hello-plugin/
├── pyproject.toml
├── openhop-plugin.json
└── hello_plugin/
    └── __init__.py
```

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "example-hello-plugin"
version = "0.1.0"
description = "A local Repeater plugin development example"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
example-hello = "hello_plugin:main"

[tool.setuptools]
packages = ["hello_plugin"]

[tool.setuptools.data-files]
"share/openhop/plugins/example.hello" = ["openhop-plugin.json"]
```

`openhop-plugin.json`:

```json
{
  "schema": 1,
  "id": "example.hello",
  "name": "Hello example",
  "version": "0.1.0",
  "description": "Logs a configured greeting without network or radio access.",
  "runtime": {"type": "python", "entrypoint": "example-hello"},
  "config": {"defaults": {"message": "Hello from a plugin"}}
}
```

`hello_plugin/__init__.py`:

```python
import json
import os
import signal
from pathlib import Path
from threading import Event


def main():
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    data = Path(os.environ["OPENHOP_PLUGIN_DATA"])
    config_path = data / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    message = config.get("message", "Hello from a plugin")
    if not isinstance(message, str):
        raise ValueError("message must be a string")
    print(f"{os.environ['OPENHOP_PLUGIN_ID']}: {message}", flush=True)
    stop.wait()
    print("Stopping", flush=True)
```

This intentionally has no network, radio, backend server, UI or runtime
dependencies. It reads configuration once; restart it to apply edits. It waits
in the foreground until a termination signal instead of exiting successfully
and being restarted as an unexpectedly exited service.

From that project directory, with Python 3.10+ and `uv` available:

```bash
uv venv --python python3 .venv
uv pip install --python .venv/bin/python build setuptools wheel
.venv/bin/python -m build --wheel
.venv/bin/python -m zipfile -l dist/example_hello_plugin-0.1.0-py3-none-any.whl
```

The wheel should include the package, `.dist-info/METADATA`,
`.dist-info/entry_points.txt`, `.dist-info/RECORD`, and:

```text
example_hello_plugin-0.1.0.data/data/share/openhop/plugins/example.hello/openhop-plugin.json
```

### Check with the real Repeater parser, without starting Repeater

Clone the public source into a new sibling directory; do not modify an existing
Repeater checkout or install Repeater/hardware dependencies. These commands pin
the inspected baseline. To test a newer version, deliberately change the SHA and
review its contract first.

```bash
git clone --no-checkout https://github.com/openhop-dev/openhop_repeater.git repeater-source
git -C repeater-source checkout --detach 13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b
PYTHONPATH="$PWD/repeater-source" .venv/bin/python validate_wheel.py
```

Create `validate_wheel.py` in the example project before the last command:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from repeater.plugins.manifest import load_manifest_from_wheel
from repeater.plugins.storage import PluginStorage

wheel = Path("dist/example_hello_plugin-0.1.0-py3-none-any.whl")
manifest = load_manifest_from_wheel(wheel)
assert (manifest.id, manifest.version) == ("example.hello", "0.1.0")
assert manifest.runtime.type == "python"
assert manifest.runtime.entrypoint == "example-hello"
with ZipFile(wheel) as archive:
    names = archive.namelist()
    manifests = [n for n in names if n.endswith("/openhop-plugin.json")]
    assert manifests == [
        "example_hello_plugin-0.1.0.data/data/share/openhop/plugins/"
        "example.hello/openhop-plugin.json"
    ]
    entrypoints = archive.read(
        "example_hello_plugin-0.1.0.dist-info/entry_points.txt"
    ).decode()
    assert "example-hello = hello_plugin:main" in entrypoints
with TemporaryDirectory(prefix="hello-plugin-validation-") as root:
    storage = PluginStorage(Path(root) / "plugins")
    storage.ensure_plugin_layout(manifest.id, manifest.version)
    storage.write_manifest(manifest.id, manifest.version, manifest)
    storage.set_current(manifest.id, manifest.version)
    storage.write_state(manifest.id, {"version": manifest.version, "enabled": False})
    storage.write_config(manifest.id, manifest.config_defaults)
    assert storage.load_current_manifest(manifest.id) == manifest
    assert storage.read_config(manifest.id) == {"message": "Hello from a plugin"}
print("PASS: wheel discovery, console metadata, manifest and temporary storage round-trip")
```

This checks the actual parser and storage implementation, not a replacement JSON
schema. It does **not** pip-install or run a plugin, start a manager, open a socket,
access hardware, or prove end-to-end installation. Before publication, test pip
installation and the lifecycle on your own isolated Repeater test deployment.

## Runtime, settings and persistent data

The launcher resolves the console script inside the release venv's `bin/`
(`Scripts/` on Windows). It runs **only that executable**, with no extra arguments,
no shell and no defined stdin protocol; stdin is not configured by the launcher.
Do not wait for interactive input. The working directory is the plugin's `data/`.
It inherits the manager environment, removes `OPENHOP_PLUGIN_GITHUB_TOKEN`, and
sets `OPENHOP_PLUGIN_ID` and `OPENHOP_PLUGIN_DATA`. No automatic `PORT`, API token,
config-path argument or special Python module-entrypoint convention is provided.

The default plugin root is under Repeater storage (commonly
`/var/lib/openhop_repeater/plugins`), configurable through `plugins.root`:

```text
<root>/example.hello/
├── releases/0.1.0/     # manifest, retained wheel, optional UI/defaults, runtime venv
├── current -> releases/0.1.0
├── data/config.json   # persistent across versions; plugin validates its keys
├── logs/plugin.log    # merged stdout/stderr, bounded capture
└── state.json         # manager-owned version/enabled metadata; do not edit
```

Use `OPENHOP_PLUGIN_DATA`, not a hard-coded installation directory. The optional
`data/runtime.json` can hold an app-written JSON object exposed through
`GET /api/plugins/runtime?id=example.hello`; it is not a command channel.

Manifest `config.defaults` supplies initial settings. Alternatively package
`config.default.json` beside the manifest using the same `data-files` table.
File defaults override matching manifest-default keys with a shallow merge.
Nonempty defaults seed `data/config.json` only when it is absent; an upgrade does
not merge new keys into existing user settings. Implement your own compatible
config/data migrations and backups. The settings editor may display defaults for
an empty saved object; inspect `saved` versus `config` in its response when debugging.

`GET /api/plugins/settings?id=example.hello` returns saved/default/editor values.
`POST /api/plugins/settings` takes `id`, an object `config`, and optional
`restart: true` (default false). The manager enforces an object and 256 KiB size
limit, not your app's field schema. A settings save can succeed even if the
requested restart fails. Never bundle real credentials in defaults or logs.
Sources: [launcher/defaults/supervision][runtime], [settings and lifecycle][manager],
[storage paths][storage], [API handlers][api].

## Add an optional application UI

Add `"ui": {"type": "application", "entry": "ui/index.html"}` and package public
assets under a `ui/` directory, for example using another setuptools data-files
table for `share/openhop/plugins/example.hello/ui`. List each asset explicitly or
use your own tested build configuration for nested assets.

Extraction finds the entry's top directory as a complete archive path component
and copies that subtree to the release. Avoid multiple unrelated `ui/` trees in
the wheel; do not rely on archive order to resolve collisions. A missing entry
produces an installer warning, so explicitly inspect the built wheel and verify
the served page. The entry cannot be at release root, use dot/parent segments,
or use reserved first directories `venv`, `data`, `logs`, `releases`, `current`
(case-insensitive); absolute/tilde paths, a hidden first directory and colons are
also rejected.

Once enabled, the entry is served at `/plugins/example.hello/`, with other URLs
relative to the entry file's parent directory (`ui/` in this example) and an
entry-document fallback for SPA routes.
Configure your frontend base path accordingly. Disabled UIs are not served.
**Treat these static assets as public:** do not include credentials, private
configuration, source maps with secrets, or runtime files. Same-origin app
JavaScript is trusted code, not a sandbox or automatic authentication boundary.
Any app backend needs its own explicit integration; declaring `ui` does not proxy
a service port. Sources: [UI validation][manifest], [asset extraction][runtime],
[static serving][static], [static security tests][static-tests].

## Local installation and lifecycle checklist

Use a trusted, disposable Repeater test installation with its plugin manager
available. These are deployment actions, separate from the safe parser check
above. Use the Plugins upload/settings controls or authenticated API endpoints:

| Action | API and behavior |
| --- | --- |
| Upload | `POST /api/plugins/install`, multipart field `wheel`; alternatively JSON `wheel_path` naming a file readable on the server/manager filesystem, not the developer's laptop. |
| Inspect | `GET /api/plugins/` or `GET /api/plugins/example.hello`. |
| Enable | `POST /api/plugins/enable`, JSON `{"id":"example.hello"}`; starts a service and exposes its UI. |
| Control | POST the same body to `/api/plugins/start`, `/stop`, `/restart`, `/disable`. Start/restart require enabled state. Stop does not disable boot startup; disable does. |
| Logs | `GET /api/plugins/logs?id=example.hello&tail=100`; stdout/stderr share `logs/plugin.log`, capped at 5 MiB while running, with bounded tail reads. |
| Remove | `DELETE /api/plugins/example.hello` keeps `data/`; `?delete_data=true` also removes it. Back up first. |

A first **local upload is disabled**; configure then enable it. A reinstall
preserves the enabled flag but the local install path does not stop/restart the
old process for you. For a local upgrade, disable first, upload a newly versioned
wheel, inspect settings/data, then enable and verify the running version.
Catalogue installation is a separate path that enables by default; catalogue
update stops the old process and preserves prior enabled state.

Releases have separate venvs and share data. Do not assume transactional upgrade
rollback: installation failures can leave partial release files; startup failure
after switching releases does not automatically restore old code/data. Keep
backups and test recovery. A Python minor-version change can trigger rebuilding
the venv from the retained wheel. That rebuild has its own backup/restore handling,
which is not a general app-upgrade rollback mechanism.

The manager starts enabled services on boot, supervises unexpected exits
(including a normal exit outside a stop path), and defaults to `FAILED` after
five exits within 60 seconds. Stop/disable send SIGTERM, then SIGKILL after the
stop budget (default five seconds), targeting the POSIX process group. Handle
SIGTERM and keep worker children in that group. `RUNNING` proves a live process,
not that your app's external connection or business function works.

Missing manager IPC gives HTTP 503; conflicting operations can report busy.
HTTP 504 with `outcome: "unknown"` means completion was not observed, **not** that
the operation was cancelled. Inspect status/progress before retrying. Venv/pip
subprocess budgets (120/300 seconds) differ from the IPC completion budget
(900 seconds). Sources: [manager][manager], [runtime][runtime], [IPC][ipc], [API][api],
[lifecycle regression tests][lifecycle-tests].

## Trust, release and validation boundaries

A separate process and venv isolate Python dependencies, **not** filesystem,
network, device access or credentials. Native plugins run under the Repeater
service account; container plugins use the configured container account. Do not
run the manager as root to fix permissions. Inherited environment and accessible
files can contain sensitive data. Process-group cleanup does not contain hostile
code that deliberately detaches.

Pip installs the wheel with `--upgrade` and resolves declared dependencies; there
is no automatic hash lock for those dependencies. A catalogue SHA-256 covers the
wheel bytes only. Current Repeater API tokens are administrator-equivalent, not
read-only or per-plugin scoped. Disclose permissions, dependencies, network
services and data handling, and install only code you trust. See the upstream
[trust discussion][overview].

The three-file example was built with Python 3.13.13, `build` 1.6.1,
setuptools 84.0.0 and wheel 0.48.0. Its parser/storage check passed against the
pinned source on both Python 3.13.13 and 3.12.3: wheel discovery, console-script
metadata and temporary storage round-trip all passed. That evidence does not claim
live API, UI, manager startup, RF, dependency-platform compatibility or production
upgrade testing. The UI extension is guidance, not part of this minimal tested
service wheel.

Before requesting catalogue review, test install/configure/enable/stop/restart,
unexpected-exit recovery, disable, upgrade with existing data and uninstall on
your own test deployment. Record its Repeater version and results, publish the
versioned wheel in your app repository, verify the downloaded release bytes and
follow the [submission guide](third-party-apps.md). Catalogue certification
profiles can impose additional packaging checks; passing this runtime guide does
not enroll your app in automatic publishing or grant approval.

[manifest]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/repeater/plugins/manifest.py
[runtime]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/repeater/plugins/runtime.py
[storage]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/repeater/plugins/storage.py
[manager]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/repeater/plugins/manager.py
[ipc]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/repeater/plugins/ipc.py
[api]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/repeater/web/plugin_endpoints.py
[static]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/repeater/web/http_server.py
[overview]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/docs/plugins.md
[static-tests]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/tests/test_plugin_static_security.py
[lifecycle-tests]: https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/tests/test_plugin_manager_lifecycle.py
