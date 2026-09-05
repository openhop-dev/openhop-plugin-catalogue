import copy

import pytest
from test_publishing_policy import p, fixtures


class AppAPI:
    def __init__(self, app_id=4844315):
        self.check = {
            "id": 1,
            "app": {"id": app_id, "slug": "openhop-catalogue-policy"},
        }
        self.writes = []

    def repo(self, path, method="GET", data=None):
        if method != "GET":
            self.writes.append((path, data))
            self.check.update(data)
        return copy.deepcopy(self.check)


def test_publish_uses_exact_policy_app_and_reads_back():
    api = AppAPI()
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    assert target["check_id"] == 1 and api.check["head_sha"] == "c" * 40
    p.complete_check(api, target, True)
    assert api.check["conclusion"] == "success"


def test_wrong_app_cannot_issue_authoritative_check():
    with pytest.raises(p.PolicyError):
        p.create_pending(AppAPI(15368), fixtures()[2], "d" * 40)


def test_wrong_head_check_cannot_be_completed():
    api = AppAPI()
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    api.check["head_sha"] = "e" * 40
    with pytest.raises(p.PolicyError):
        p.complete_check(api, target, True)


def test_readback_failure_not_success():
    api = AppAPI()
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    old = api.repo

    def changed(path, method="GET", data=None):
        result = old(path, method, data)
        if method == "GET" and result.get("status") == "completed":
            result["conclusion"] = "failure"
        return result

    api.repo = changed
    with pytest.raises(p.PolicyError):
        p.complete_check(api, target, True)


def test_execution_guard_rejects_nonmain_and_wrong_repository(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", p.REPOSITORY)
    monkeypatch.setenv("GITHUB_REF", "refs/pull/12/merge")
    monkeypatch.setenv("POLICY_CODE_SHA", "d" * 40)
    with pytest.raises(p.PolicyError):
        p.trusted_context(type("A", (), {"main": lambda _: "d" * 40})())


def test_noncertified_never_auto_enabled(monkeypatch):
    monkeypatch.setenv("CATALOGUE_POLICY_AUTOMERGE_ENABLED", "true")

    class Never:
        def repo(self, *_, **__):
            pytest.fail("manual PR caused API call")

    with pytest.raises(p.PolicyError):
        p.enable_auto(Never(), {"certified": False}, {})


def test_missing_activation_flag_never_auto_enabled(monkeypatch):
    monkeypatch.delenv("CATALOGUE_POLICY_AUTOMERGE_ENABLED", raising=False)
    with pytest.raises(p.PolicyError):
        p.enable_auto(None, {"certified": True}, {})
