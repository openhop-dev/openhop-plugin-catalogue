"""Trusted registrations select policy; proposals cannot choose their profile."""

import copy
import hashlib
import json

import pytest
from test_policy_orchestration import FakeAPI
from test_policy_release import wheel
from test_publishing_policy import ROOT, fixtures, p


def nomad():
    base, _, pr = fixtures()
    candidate = copy.deepcopy(base)
    item = candidate["plugins"][0]
    item.update(
        version="0.1.2",
        source_revision="f" * 40,
        sha256="b" * 64,
        wheel_url="https://github.com/openhop-dev/openhop-nomad-plugin/releases/download/v0.1.2/openhop_nomad_plugin-0.1.2-py3-none-any.whl",
    )
    pr["head"]["ref"] = "automation/openhop-nomad-v0.1.2"
    return base, candidate, pr


def nomad_wheel(mutation=None):
    def convert(files):
        files.clear()
        prefix = (
            "openhop_nomad_plugin-0.1.2.data/data/share/openhop/plugins/openhop.nomad/"
        )
        files.update(
            {
                prefix
                + "openhop-plugin.json": json.dumps(
                    {
                        "schema": 1,
                        "id": "openhop.nomad",
                        "version": "0.1.2",
                        "ui": {"type": "application", "entry": "ui/index.html"},
                        "runtime": {
                            "type": "python",
                            "entrypoint": "meshcore-nomad-bridge",
                        },
                    }
                ).encode(),
                prefix + "config.default.json": b"{}",
                prefix + "ui/index.html": b"test",
                prefix + "ui/app.js": b"test",
                prefix + "ui/styles.css": b"test",
                "meshcore_nomad_bridge/__init__.py": b"",
                "meshcore_nomad_bridge/main.py": b'raise RuntimeError("never execute")',
                "openhop_nomad_plugin-0.1.2.dist-info/METADATA": b"Name: openhop-nomad-plugin\nVersion: 0.1.2\n",
                "openhop_nomad_plugin-0.1.2.dist-info/WHEEL": b"Wheel-Version: 1.0\n",
                "openhop_nomad_plugin-0.1.2.dist-info/entry_points.txt": b"[console_scripts]\nmeshcore-nomad-bridge = meshcore_nomad_bridge.main:main\n",
            }
        )
        if mutation:
            mutation(files)

    # Reuse the existing fixture's RECORD construction, then rename its RECORD.
    import io
    import zipfile

    raw = wheel(convert)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(out, "w") as dst:
        for n in src.namelist():
            data = src.read(n)
            if n == "waev_outpost_plugin-1.2.3.dist-info/RECORD":
                data = data.replace(
                    b"waev_outpost_plugin-1.2.3.dist-info/RECORD",
                    b"openhop_nomad_plugin-0.1.2.dist-info/RECORD",
                )
                n = "openhop_nomad_plugin-0.1.2.dist-info/RECORD"
            dst.writestr(n, data)
    return out.getvalue()


def generic_registry(tmp_path):
    data = json.loads((ROOT / "approved-apps.json").read_text())
    for c in data["apps"]:
        if c["plugin"] == "waev.outpost":
            c.update(package_profile="static-ui-v1", package_config={})
        else:
            c.update(
                package_profile="python-service-v1",
                package_config={
                    "package_root": "meshcore_nomad_bridge",
                    "module": "meshcore_nomad_bridge.main",
                    "console_script": "meshcore-nomad-bridge",
                    "callable": "main",
                },
            )
    third = copy.deepcopy(data["apps"][1])
    third.update(
        plugin="synthetic.service",
        artifact_repository="example/synthetic-service",
        source_repository="example/synthetic-service",
        distribution="synthetic-service",
        wheel_basename="synthetic_service",
        branch_prefix="automation/synthetic-service-v",
        package_config={
            "package_root": "different_package",
            "module": "different_package.worker",
            "console_script": "different-service",
            "callable": "run",
        },
    )
    data["apps"].append(third)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data))
    return path


def test_third_python_app_is_registration_only(tmp_path, monkeypatch):
    registry = p.load_registry(generic_registry(tmp_path))
    monkeypatch.setattr(p, "load_registry", lambda: registry)
    b, c, pr = nomad()
    for document in (b, c):
        document["plugins"][0].update(
            id="synthetic.service",
            repository="example/synthetic-service",
            distribution="synthetic-service",
        )
    item = c["plugins"][0]
    item["wheel_url"] = p.wheel_url(item["version"], item["id"])
    pr["head"]["ref"] = "automation/synthetic-service-v0.1.2"
    assert p.certified_entry(pr, ["catalogue.json"], b, c) == item

    def convert(files):
        replacements = [
            ("openhop_nomad_plugin", "synthetic_service"),
            ("openhop-nomad-plugin", "synthetic-service"),
            ("openhop.nomad", "synthetic.service"),
            ("meshcore_nomad_bridge/main.py", "different_package/worker.py"),
            ("meshcore_nomad_bridge.main:main", "different_package.worker:run"),
            ("meshcore_nomad_bridge", "different_package"),
            ("meshcore-nomad-bridge", "different-service"),
        ]
        for name, payload in list(files.items()):
            del files[name]
            for old, new in replacements:
                name = name.replace(old, new)
                payload = payload.replace(old.encode(), new.encode())
            files[name] = payload

    # The shared fixture creates its RECORD after conversion; rename that self row too.
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(nomad_wheel(convert))) as src, zipfile.ZipFile(
        out, "w"
    ) as dst:
        for name in src.namelist():
            payload = src.read(name)
            if name.endswith("/RECORD"):
                payload = payload.replace(b"openhop_nomad_plugin", b"synthetic_service")
                name = name.replace("openhop_nomad_plugin", "synthetic_service")
            dst.writestr(name, payload)
    raw = out.getvalue()
    item["sha256"] = hashlib.sha256(raw).hexdigest()
    p.verify_wheel(raw, item)
    # Changing the trusted contract alone must reject the previously valid wheel.
    for field, wrong in [
        ("package_root", "other"),
        ("module", "different_package.missing"),
        ("console_script", "other-service"),
        ("callable", "other"),
    ]:
        config = registry[item["id"]]["package_config"]
        original = config[field]
        config[field] = wrong
        with pytest.raises(p.PolicyError):
            p.verify_wheel(raw, item)
        config[field] = original


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_root", "../evil"),
        ("package_root", ".*"),
        ("package_root", "class"),
        ("module", "evil.worker"),
        ("module", "different_package.worker.extra"),
        ("console_script", "../evil"),
        ("callable", "run()"),
        ("callable", "class"),
        ("extra", "anything"),
        ("module", None),
    ],
)
def test_python_contract_validation(tmp_path, field, value):
    path = generic_registry(tmp_path)
    data = json.loads(path.read_text())
    data["apps"][-1]["package_config"][field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(p.PolicyError):
        p.load_registry(path)


@pytest.mark.parametrize("attack", ["missing", "static-config", "legacy-profile"])
def test_profile_contract_required(tmp_path, attack):
    path = generic_registry(tmp_path)
    data = json.loads(path.read_text())
    if attack == "missing":
        del data["apps"][-1]["package_config"]["module"]
    elif attack == "static-config":
        data["apps"][0]["package_config"] = data["apps"][-1]["package_config"]
    else:
        data["apps"][-1]["package_profile"] = "nomad-python-v1"
    path.write_text(json.dumps(data))
    with pytest.raises(p.PolicyError):
        p.load_registry(path)


def test_nomad_certification():
    b, c, pr = nomad()
    assert p.certified_entry(pr, ["catalogue.json"], b, c) == c["plugins"][0]


@pytest.mark.parametrize(
    "attack",
    [
        "other",
        "unknown",
        "branch",
        "downgrade",
        "repository",
        "distribution",
        "profile",
    ],
)
def test_nomad_untrusted_changes_not_certified(attack):
    b, c, pr = nomad()
    if attack == "other":
        c["plugins"][1]["version"] = "9.9.9"
    if attack == "unknown":
        c["plugins"][0]["id"] = "unknown.app"
    if attack == "branch":
        pr["head"]["ref"] = "automation/waev-outpost-v0.1.2"
    if attack == "downgrade":
        c["plugins"][0]["version"] = "0.0.1"
    if attack in {"repository", "distribution"}:
        c["plugins"][0][attack] = "evil"
    if attack == "profile":
        c["plugins"][0]["package_profile"] = "outpost-ui-v1"
    assert p.certified_entry(pr, ["catalogue.json"], b, c) is None


def test_nomad_data_files_profile():
    item = nomad()[1]["plugins"][0]
    raw = nomad_wheel()
    item["sha256"] = hashlib.sha256(raw).hexdigest()
    p.verify_wheel(raw, item)


@pytest.mark.parametrize(
    "attack",
    [
        "runtime",
        "entrypoint",
        "extra",
        "root-manifest",
        "other-package",
        "record",
        "manifest",
    ],
)
def test_nomad_profile_rejects(attack):
    def mutate(files):
        manifest = next(n for n in files if n.endswith("openhop-plugin.json"))
        if attack in {"runtime", "manifest"}:
            m = json.loads(files[manifest])
            m["runtime"]["type"] = "shell"
            if attack == "manifest":
                m["id"] = "waev.outpost"
            files[manifest] = json.dumps(m).encode()
        if attack == "entrypoint":
            files["openhop_nomad_plugin-0.1.2.dist-info/entry_points.txt"] = (
                b"[console_scripts]\nmeshcore-nomad-bridge = evil:main\n"
            )
        if attack == "extra":
            files["setup.py"] = b"evil"
        if attack == "root-manifest":
            files["openhop-plugin.json"] = files[manifest]
        if attack == "other-package":
            files["evil/__init__.py"] = b"evil"
        if attack == "record":
            files["openhop_nomad_plugin-0.1.2.dist-info/other/RECORD"] = b""

    raw = nomad_wheel(mutate)
    item = nomad()[1]["plugins"][0]
    item["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(p.PolicyError):
        p.verify_wheel(raw, item)


class NomadRelease:
    def __init__(self, attack=None):
        self.attack = attack

    def call(self, path):
        assert "/openhop-dev/openhop-nomad-plugin/" in path
        if "/releases/" not in path:
            return {"object": {"type": "commit", "sha": "f" * 40}}
        item = nomad()[1]["plugins"][0]
        url = item["wheel_url"]
        name = url.rsplit("/", 1)[1]
        names = [name, "openhop-nomad-plugin-v0.1.2-wheel.zip"]
        if self.attack == "extra":
            names.append("extra.zip")
        if self.attack == "missing":
            names.pop()
        if self.attack == "zip":
            names[1] = "wrong.zip"
        return {
            "tag_name": "v0.1.2",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": n,
                    "size": 123,
                    "browser_download_url": url.rsplit("/", 1)[0] + "/" + n,
                }
                for n in names
            ],
        }


def test_nomad_release_snapshot_detects_companion_asset_change():
    api = NomadRelease()
    item = nomad()[1]["plugins"][0]
    before = p.verify_release(api, item)
    original = api.call

    def changed(path):
        result = original(path)
        if "/releases/" in path:
            result["assets"][1]["size"] += 1
        return result

    api.call = changed
    assert p.verify_release(api, item) != before


def test_nomad_release_source_binding():
    item = nomad()[1]["plugins"][0]
    assert p.verify_release(NomadRelease(), item)["source_sha"] == "f" * 40
    item["source_revision"] = "a" * 40
    with pytest.raises(p.PolicyError):
        p.verify_release(NomadRelease(), item)


@pytest.mark.parametrize("attack", ["extra", "missing", "zip"])
def test_nomad_exact_asset_contract(attack):
    with pytest.raises(p.PolicyError):
        p.verify_release(NomadRelease(attack), nomad()[1]["plugins"][0])


@pytest.mark.parametrize(
    "attack",
    [
        "unknown-profile",
        "duplicate",
        "extra-field",
        "bad-repo",
        "bad-prefix",
        "bad-app",
        "bad-basename",
        "source-mode",
        "missing",
    ],
)
def test_registry_fails_closed(attack, tmp_path):
    assert hasattr(p, "load_registry"), "trusted registry loader missing"
    data = json.loads((ROOT / "approved-apps.json").read_text())
    c = data["apps"][0]
    if attack == "unknown-profile":
        c["package_profile"] = "unknown"
    if attack == "duplicate":
        data["apps"].append(copy.deepcopy(c))
    if attack == "extra-field":
        c["fields"] = ["name"]
    if attack == "bad-repo":
        c["artifact_repository"] = "https://evil/x"
    if attack == "bad-prefix":
        c["branch_prefix"] = "../"
    if attack == "bad-app":
        c["publisher_app_id"] = True
    if attack == "bad-basename":
        c["wheel_basename"] = "../evil"
    if attack == "source-mode":
        c["source_verification"] = "ignore"
    if attack == "missing":
        del c["distribution"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data))
    with pytest.raises(p.PolicyError):
        p.load_registry(path)


def test_nomad_receipt_binds_selected_app(monkeypatch):
    api = FakeAPI()
    api.base, api.candidate, api.pull = nomad()
    api.run["head_branch"] = api.pull["head"]["ref"]
    api.reviews = []
    raw = nomad_wheel()
    api.candidate["plugins"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(p, "download", lambda _: raw)
    original = p.verify_release
    monkeypatch.setattr(
        p,
        "verify_release",
        lambda api, item: dict(original(NomadRelease(), item), asset_size=len(raw)),
    )
    result = p.evaluate(api, 12)
    assert result["certified"] and result["plugin"] == "openhop.nomad"
    assert p.evaluate(api, 12, receipt=result) == result
    result["plugin"] = "waev.outpost"
    with pytest.raises(p.PolicyError):
        p.evaluate(api, 12, receipt=result)
