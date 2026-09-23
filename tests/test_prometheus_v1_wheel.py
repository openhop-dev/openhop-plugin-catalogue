"""Exercise the trusted Prometheus profile with a portable wheel fixture."""

import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import pytest

from test_publishing_policy import p


DATA = (
    "openhop_prometheus_plugin-1.0.0.data/data/share/openhop/plugins/"
    "openhop.prometheus/ui/assets/"
)
RECORD = "openhop_prometheus_plugin-1.0.0.dist-info/RECORD"
ASSETS = ("prometheus-logo.svg", "PROMETHEUS-LICENSE", "PROVENANCE.md")


@pytest.fixture(scope="module")
def local_wheel():
    prefix = DATA.removesuffix("ui/assets/")
    files = {
        prefix + "openhop-plugin.json": json.dumps({
            "schema": 1, "id": "openhop.prometheus", "version": "1.0.0",
            "runtime": {"type": "python", "entrypoint": "openhop-prometheus"},
            "ui": {"type": "application", "entry": "ui/index.html"},
        }).encode(),
        prefix + "config.default.json": b"{}",
        prefix + "ui/index.html": b"<html></html>",
        prefix + "ui/app.js": b"",
        prefix + "ui/styles.css": b"",
        "openhop_prometheus_plugin-1.0.0.dist-info/METADATA": b"Name: openhop-prometheus-plugin\nVersion: 1.0.0\n",
        "openhop_prometheus_plugin-1.0.0.dist-info/WHEEL": b"Wheel-Version: 1.0\n",
        "openhop_prometheus_plugin-1.0.0.dist-info/entry_points.txt": b"[console_scripts]\nopenhop-prometheus = openhop_prometheus_plugin.main:main\n",
        "openhop_prometheus_plugin-1.0.0.dist-info/licenses/LICENSE": b"MIT",
    }
    for name in ("__init__.py", "main.py", "config.py", "metrics.py", "state.py", "manager.py", "model.py", "http_server.py", "actions.py", "runtime_snapshot.py"):
        files["openhop_prometheus_plugin/" + name] = b""
    for name in ("__init__.py", "base.py", "plugin.py", "repeater.py"):
        files["openhop_prometheus_plugin/collectors/" + name] = b""
    for asset in ASSETS:
        files[DATA + asset] = b"bundled asset"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return repack(out.getvalue())


def test_optional_real_build_from_environment():
    path = os.environ.get("PROMETHEUS_V1_WHEEL")
    if not path:
        pytest.skip("set PROMETHEUS_V1_WHEEL to validate an actual built artifact")
    raw = Path(path).read_bytes()
    p.verify_wheel(raw, item(raw))


def item(raw):
    registration = p.registration("openhop.prometheus")
    assert registration["package_profile"] == "python-service-v1"
    assert registration["release_assets"] == "wheel-only"
    assert registration["source_verification"] == "public-tag"
    return {
        "id": registration["plugin"],
        "repository": registration["artifact_repository"],
        "distribution": registration["distribution"],
        "version": "1.0.0",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def repack(raw, *, omit=(), extra=None):
    """Recompute RECORD so negative tests reach the path policy, not the digest gate."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if name not in omit and name != RECORD}
    if extra is not None:
        files[extra] = b"unauthorized"
    rows = []
    for name, payload in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
        rows.append((name, "sha256=" + digest, str(len(payload))))
    rows.append((RECORD, "", ""))
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    files[RECORD] = buffer.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return output.getvalue()


def test_exact_local_prometheus_v1_wheel(local_wheel):
    p.verify_wheel(local_wheel, item(local_wheel))
    with zipfile.ZipFile(io.BytesIO(local_wheel)) as archive:
        for asset in ASSETS:
            assert DATA + asset in archive.namelist()


@pytest.mark.parametrize("asset", ASSETS)
def test_each_artwork_provenance_file_is_required(local_wheel, asset):
    raw = repack(local_wheel, omit=(DATA + asset,))
    with pytest.raises(p.PolicyError, match="required wheel member missing"):
        p.verify_wheel(raw, item(raw))


@pytest.mark.parametrize(
    "extra",
    [
        DATA + "unreviewed.svg",
        DATA + "PROMETHEUS-LICENSE.bak",
        DATA + "nested/PROVENANCE.md",
        "openhop_prometheus_plugin-1.0.0.data/data/share/openhop/plugins/openhop.prometheus/ui/extra.js",
        "unrelated/__init__.py",
    ],
)
def test_extra_record_covered_files_are_rejected(local_wheel, extra):
    raw = repack(local_wheel, extra=extra)
    with pytest.raises(p.PolicyError, match="unexpected wheel member"):
        p.verify_wheel(raw, item(raw))
