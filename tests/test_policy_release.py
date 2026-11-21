import base64
import csv
import hashlib
import io
import json
import zipfile

import pytest
from test_publishing_policy import p, fixtures


def wheel(mutation=None):
    manifest = json.dumps(
        {
            "id": "waev.outpost",
            "schema": 1,
            "version": "1.2.3",
            "ui": {"type": "application", "entry": "ui/index.html"},
            "runtime": {"type": "python", "entrypoint": "waev-outpost-recorder"},
        }
    ).encode()
    dist = "waev_outpost_plugin-1.2.3.dist-info/"
    files = {
        "openhop-plugin.json": manifest,
        "share/openhop/plugins/waev.outpost/openhop-plugin.json": manifest,
        "ui/index.html": b"<html>test</html>",
        "ui/assets/app.js": b"test",
        "waev_outpost_recorder/__init__.py": b"",
        "waev_outpost_recorder/__main__.py": b'raise RuntimeError("never execute")',
        "waev_outpost_recorder/store.py": b'raise RuntimeError("never execute")',
        dist + "METADATA": b"Name: waev-outpost-plugin\nVersion: 1.2.3\n",
        dist + "WHEEL": b"Wheel-Version: 1.0\n",
        dist + "entry_points.txt": b"[console_scripts]\n"
        b"waev-outpost-recorder = waev_outpost_recorder.__main__:main\n",
    }
    if mutation:
        mutation(files)
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for name, data in files.items():
        writer.writerow(
            [
                name,
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .decode()
                .rstrip("="),
                str(len(data)),
            ]
        )
    writer.writerow([dist + "RECORD", "", ""])
    files[dist + "RECORD"] = record.getvalue().encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def test_public_wheel_verified_without_execution():
    raw = wheel()
    item = fixtures()[1]["plugins"][1]
    item["sha256"] = hashlib.sha256(raw).hexdigest()
    p.verify_wheel(raw, item)


@pytest.mark.parametrize(
    "attack",
    [
        "sha",
        "version",
        "distribution",
        "manifest",
        "path",
        "python",
        "record",
        "oversize",
        "duplicate",
        "no-runtime",
        "runtime-extra",
        "entrypoint",
        "second-script",
        "second-section",
        "no-entry-points",
        "missing-module",
        "missing-init",
        "other-package",
        "nested-package",
        "package-data",
        "data-layout",
        "no-wheel-file",
        "dependency",
    ],
)
def test_wheel_attacks_rejected(attack, monkeypatch):
    item = fixtures()[1]["plugins"][1]

    def mutate(files):
        meta = "waev_outpost_plugin-1.2.3.dist-info/METADATA"
        entry_points = "waev_outpost_plugin-1.2.3.dist-info/entry_points.txt"
        if attack == "version":
            files[meta] = b"Name: waev-outpost-plugin\nVersion: 1.2.4\n"
        if attack == "distribution":
            files[meta] = b"Name: evil\nVersion: 1.2.3\n"
        if attack == "manifest":
            files["openhop-plugin.json"] = b"{}"
        if attack == "path":
            files["ui/../evil"] = b"x"
        if attack == "python":
            files["setup.py"] = b'raise Exception("must not execute")'
        if attack in {"no-runtime", "runtime-extra"}:
            for name in (
                "openhop-plugin.json",
                "share/openhop/plugins/waev.outpost/openhop-plugin.json",
            ):
                m = json.loads(files[name])
                if attack == "no-runtime":
                    del m["runtime"]
                else:
                    m["runtime"]["args"] = ["--anything"]
                files[name] = json.dumps(m).encode()
        if attack == "entrypoint":
            files[entry_points] = (
                b"[console_scripts]\n"
                b"waev-outpost-recorder = waev_outpost_recorder.store:main\n"
            )
        if attack == "second-script":
            files[entry_points] += b"other = waev_outpost_recorder.__main__:main\n"
        if attack == "second-section":
            files[entry_points] += (
                b"[gui_scripts]\nother = waev_outpost_recorder.__main__:main\n"
            )
        if attack == "no-entry-points":
            del files[entry_points]
        if attack == "missing-module":
            del files["waev_outpost_recorder/__main__.py"]
        if attack == "missing-init":
            del files["waev_outpost_recorder/__init__.py"]
        if attack == "other-package":
            files["evil/__init__.py"] = b"evil"
        if attack == "nested-package":
            files["waev_outpost_recorder/vendor/__init__.py"] = b"evil"
        if attack == "package-data":
            files["waev_outpost_recorder/payload.so"] = b"evil"
        if attack == "data-layout":
            # The Python-service data prefix belongs to another profile.
            files[
                "waev_outpost_plugin-1.2.3.data/data/share/openhop/plugins/"
                "waev.outpost/config.default.json"
            ] = b"{}"
        if attack == "no-wheel-file":
            del files["waev_outpost_plugin-1.2.3.dist-info/WHEEL"]
        if attack == "dependency":
            files[meta] += b"Requires-Dist: anything\n"

    raw = wheel(mutate)
    if attack in {"record", "duplicate"}:
        out = io.BytesIO(raw)
        with zipfile.ZipFile(out, "a") as archive:
            if attack == "record":
                archive.writestr("ui/unrecorded", b"x")
            else:
                with pytest.warns(UserWarning):
                    archive.writestr("ui/index.html", b"other")
        raw = out.getvalue()
    item["sha256"] = hashlib.sha256(raw).hexdigest()
    if attack == "sha":
        item["sha256"] = "0" * 64
    if attack == "oversize":
        monkeypatch.setattr(p, "MAX_UNPACKED", 5)
    with pytest.raises((p.PolicyError, ValueError)):
        p.verify_wheel(raw, item)


class ReleaseAPI:
    def __init__(self, source="a" * 40):
        self.source = source

    def call(self, path):
        if "/releases/tags/" in path:
            return {
                "tag_name": "v1.2.3",
                "draft": False,
                "prerelease": False,
                "immutable": False,
                "assets": [
                    {
                        "name": "waev_outpost_plugin-1.2.3-py3-none-any.whl",
                        "browser_download_url": p.wheel_url("1.2.3"),
                        "size": 123,
                    }
                ],
            }
        if "/pymc_console/" in path:
            return {"object": {"type": "commit", "sha": self.source}}
        return {"object": {"type": "commit", "sha": "f" * 40}}


def test_versioned_release_not_required_to_be_host_immutable():
    p.verify_release(ReleaseAPI(), fixtures()[1]["plugins"][1])


def test_source_revision_must_be_literal_sha():
    item = fixtures()[1]["plugins"][1]
    item["source_revision"] = "main"
    with pytest.raises(p.PolicyError):
        p.verify_release(ReleaseAPI(), item)


def test_private_source_is_publisher_assertion_not_queried():
    class Inaccessible(ReleaseAPI):
        def call(self, path):
            if "/pymc_console/" in path:
                raise p.PolicyError("unavailable")
            return super().call(path)

    result = p.verify_release(Inaccessible(), fixtures()[1]["plugins"][1])
    assert result["source_sha"] == "a" * 40


def test_bounded_body_and_truncated_length():
    class Body(io.BytesIO):
        headers = {}

    with pytest.raises(p.PolicyError):
        p.bounded_read(Body(b"abcdef"), 5)
    body = Body(b"abc")
    body.headers = {"Content-Length": "6"}
    with pytest.raises(p.PolicyError):
        p.bounded_read(body, 10)


def test_deadline_interrupts_real_http_chunk_header():
    import http.client
    import socket

    left, right = socket.socketpair()
    try:
        right.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1")
        response = http.client.HTTPResponse(left)
        response.begin()
        with pytest.raises(p.PolicyError, match="deadline"):
            with p.deadline(0.05):
                p.bounded_read(response, 100)
    finally:
        left.close()
        right.close()
