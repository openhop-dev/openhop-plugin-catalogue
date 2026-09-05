"""Catalogue-owned policy: untrusted PR data never grants authority."""

import copy
import json
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publishing_policy", ROOT / "scripts/publishing_policy.py"
)
p = importlib.util.module_from_spec(SPEC) if SPEC else None
if SPEC and SPEC.loader and (ROOT / "scripts/publishing_policy.py").exists():
    SPEC.loader.exec_module(p)


def test_policy_exists():
    assert hasattr(p, "certified_entry"), (
        "missing catalogue-owned policy implementation"
    )


def fixtures():
    base = json.loads((ROOT / "catalogue.json").read_text())
    candidate = copy.deepcopy(base)
    item = candidate["plugins"][1]
    item.update(
        version="1.2.3",
        source_revision="a" * 40,
        sha256="b" * 64,
        wheel_url="https://github.com/Treehouse-00/waev-outpost-plugin/releases/download/v1.2.3/waev_outpost_plugin-1.2.3-py3-none-any.whl",
    )
    pr = {
        "number": 12,
        "state": "open",
        "draft": False,
        "user": {
            "id": 325431437,
            "login": "openhop-catalogue-publisher[bot]",
            "type": "Bot",
        },
        "head": {
            "sha": "c" * 40,
            "ref": "automation/waev-outpost-v1.2.3",
            "repo": {"full_name": "openhop-dev/openhop-plugin-catalogue"},
        },
        "base": {
            "sha": "d" * 40,
            "ref": "main",
            "repo": {"full_name": "openhop-dev/openhop-plugin-catalogue"},
        },
    }
    return base, candidate, pr


def test_certified_exact_delta():
    base, candidate, pr = fixtures()
    assert (
        p.certified_entry(pr, ["catalogue.json"], base, candidate)
        == candidate["plugins"][1]
    )


@pytest.mark.parametrize(
    "field",
    [
        "name",
        "logo",
        "description",
        "tags",
        "repository",
        "distribution",
        "min_repeater_version",
        "homepage",
        "category",
        "id",
    ],
)
def test_branding_and_nonrelease_fields_are_manual(field):
    base, candidate, pr = fixtures()
    candidate["plugins"][1][field] = "forbidden"
    assert p.certified_entry(pr, ["catalogue.json"], base, candidate) is None


@pytest.mark.parametrize(
    "attack",
    [
        "fork",
        "login",
        "id",
        "branch",
        "workflow",
        "other",
        "schema",
        "duplicate",
        "reorder",
        "downgrade",
        "same-version",
        "extra-field",
    ],
)
def test_certification_negative(attack):
    base, candidate, pr = fixtures()
    files = ["catalogue.json"]
    if attack == "fork":
        pr["head"]["repo"]["full_name"] = "evil/fork"
    if attack == "login":
        pr["user"]["login"] = "github-actions[bot]"
    if attack == "id":
        pr["user"]["id"] = 123
    if attack == "branch":
        pr["head"]["ref"] = "main"
    if attack == "workflow":
        files.append(".github/workflows/validate.yml")
    if attack == "other":
        candidate["plugins"][0]["name"] = "altered"
    if attack == "schema":
        candidate["schema"] = 3
    if attack == "duplicate":
        candidate["plugins"].append(candidate["plugins"][1])
    if attack == "reorder":
        candidate["plugins"].reverse()
    if attack == "downgrade":
        candidate["plugins"][1]["version"] = "0.0.1"
    if attack == "same-version":
        candidate["plugins"][1]["version"] = base["plugins"][1]["version"]
    if attack == "extra-field":
        candidate["plugins"][1]["new"] = True
    assert p.certified_entry(pr, files, base, candidate) is None


def review(state="APPROVED", sha="c" * 40, rid=1, uid=7):
    return {
        "id": rid,
        "state": state,
        "commit_id": sha,
        "user": {"id": uid, "login": "maintainer", "type": "User"},
    }


def test_current_maintainer_approval():
    _, _, pr = fixtures()
    assert p.approved(pr, [review()], lambda _: "write")


@pytest.mark.parametrize(
    "reviews,permission",
    [
        ([], "admin"),
        ([review(sha="a" * 40)], "admin"),
        ([review("DISMISSED")], "admin"),
        ([review(), review("CHANGES_REQUESTED", rid=2)], "admin"),
        ([review()], "read"),
        ([review(uid=325431437)], "admin"),
    ],
)
def test_stale_revoked_self_or_unapproved_denied(reviews, permission):
    assert not p.approved(fixtures()[2], reviews, lambda _: permission)


def test_comment_does_not_revoke_but_dismissal_does():
    pr = fixtures()[2]
    assert p.approved(pr, [review(), review("COMMENTED", rid=2)], lambda _: "maintain")
    assert not p.approved(
        pr, [review(), review("DISMISSED", rid=2)], lambda _: "maintain"
    )


def test_changes_requested_by_another_maintainer_blocks():
    assert not p.approved(
        fixtures()[2], [review(), review("CHANGES_REQUESTED", uid=8)], lambda _: "admin"
    )


@pytest.mark.parametrize("change", ["head", "base", "closed", "draft", "wrong-base"])
def test_fresh_ref_guard(change):
    pr = fixtures()[2]
    now = copy.deepcopy(pr)
    if change in ("head", "base"):
        now[change]["sha"] = "e" * 40
    if change == "closed":
        now["state"] = "closed"
    if change == "draft":
        now["draft"] = True
    if change == "wrong-base":
        now["base"]["ref"] = "dev"
    with pytest.raises(p.PolicyError):
        p.assert_fresh(pr, now, pr["base"]["sha"])


def test_guard_requires_current_main():
    pr = fixtures()[2]
    with pytest.raises(p.PolicyError):
        p.assert_fresh(pr, pr, "f" * 40)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a",
        "https://evil.example/a",
        "https://github.com@evil.example/a",
        "https://github.com:444/a",
        "https://api.github.com/a",
        "https://release-assets.githubusercontent.com.evil/a",
    ],
)
def test_unsafe_redirect_denied_before_request(url):
    with pytest.raises(p.PolicyError):
        p.SafeRedirect().redirect_request(None, None, 302, "", {}, url)


def test_api_token_never_sent_to_download(monkeypatch):
    seen = []

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, n):
            return b""

    class Opener:
        def open(self, request, timeout):
            seen.append(dict(request.header_items()))
            return Response()

    monkeypatch.setattr(p.urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setenv("GH_TOKEN", "secret-api-token")
    assert (
        p.download(
            "https://github.com/Treehouse-00/waev-outpost-plugin/releases/download/v1.2.3/x.whl"
        )
        == b""
    )
    assert all("Authorization" not in h for h in seen)


def test_missing_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(p.PolicyError):
        p.API()


def test_strict_json_duplicate_keys():
    with pytest.raises(p.PolicyError):
        p.strict_json('{"plugins":[],"plugins":[]}')
