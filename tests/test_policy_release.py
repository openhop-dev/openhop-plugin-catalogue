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
        }
    ).encode()
    dist = "waev_outpost_plugin-1.2.3.dist-info/"
    files = {
        "openhop-plugin.json": manifest,
        "share/openhop/plugins/waev.outpost/openhop-plugin.json": manifest,
        "ui/index.html": b"<html>test</html>",
        dist + "METADATA": b"Name: waev-outpost-plugin\nVersion: 1.2.3\n",
        dist + "WHEEL": b"Wheel-Version: 1.0\n",
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
    ],
)
def test_wheel_attacks_rejected(attack, monkeypatch):
    item = fixtures()[1]["plugins"][1]

    def mutate(files):
        meta = "waev_outpost_plugin-1.2.3.dist-info/METADATA"
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
