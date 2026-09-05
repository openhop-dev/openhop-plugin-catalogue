import copy
import json
from pathlib import Path

import pytest
from test_publishing_policy import p, fixtures, review


class FakeAPI:
    def __init__(self, manual=False):
        self.base, self.candidate, self.pull = fixtures()
        if manual:
            self.pull["user"] = {"id": 33, "login": "contributor", "type": "User"}
            self.pull["head"]["repo"]["full_name"] = "contributor/fork"
        self.reviews = [review()]
        self.run = {
            "id": 123,
            "head_sha": self.pull["head"]["sha"],
            "event": "pull_request",
            "path": ".github/workflows/validate.yml",
            "conclusion": "success",
            "status": "completed",
            "pull_requests": [{"number": 12}],
            "workflow_id": 99,
            "head_repository": copy.deepcopy(self.pull["head"]["repo"]),
            "head_branch": self.pull["head"]["ref"],
        }
        self.job = {
            "id": 456,
            "name": "validate",
            "conclusion": "success",
            "status": "completed",
            "check_run_url": "https://api.github.com/repos/openhop-dev/openhop-plugin-catalogue/check-runs/456",
        }
        self.check = {
            "app": {"id": 15368},
            "head_sha": self.pull["head"]["sha"],
            "name": "validate",
            "conclusion": "success",
            "status": "completed",
        }

    def main(self):
        return self.pull["base"]["sha"]

    def pr(self, number):
        return copy.deepcopy(self.pull)

    def catalogue(self, sha):
        return self.base if sha == self.pull["base"]["sha"] else self.candidate

    def pages(self, path, key=None):
        if "/files" in path:
            return [{"filename": "catalogue.json", "status": "modified"}]
        if "/reviews" in path:
            return copy.deepcopy(self.reviews)
        if "/runs?" in path:
            return [self.run]
        if "/jobs" in path:
            return [self.job]
        raise AssertionError(path)

    def repo(self, path, **_):
        if path == "/actions/workflows/validate.yml":
            return {"id": 99, "path": ".github/workflows/validate.yml"}
        if "/check-runs/" in path:
            return self.check
        if "/permission" in path:
            return {"permission": "write"}
        if "/compare/" in path:
            return {"merge_base_commit": {"sha": self.main()}}
        if "/git/trees/" in path:
            return {
                "tree": [{"path": "catalogue.json", "mode": "100644", "type": "blob"}]
            }
        raise AssertionError(path)


def test_manual_fork_current_approval_passes_without_download(monkeypatch):
    api = FakeAPI(manual=True)
    monkeypatch.setattr(
        p, "download", lambda _: pytest.fail("ordinary PR downloaded wheel")
    )
    result = p.evaluate(api, 12)
    assert result["allowed"] and not result["certified"]


def test_manual_without_approval_is_denied():
    api = FakeAPI(manual=True)
    api.reviews = []
    with pytest.raises(p.PolicyError):
        p.evaluate(api, 12)


@pytest.mark.parametrize(
    "forgery",
    [
        "workflow-id",
        "path",
        "event",
        "head",
        "pr",
        "job-name",
        "app",
        "pending",
        "failed",
    ],
)
def test_validate_provenance_not_generic_context(forgery):
    api = FakeAPI(manual=True)
    if forgery == "workflow-id":
        api.run["workflow_id"] = 88
    if forgery == "path":
        api.run["path"] = ".github/workflows/forged.yml"
    if forgery == "event":
        api.run["event"] = "push"
    if forgery == "head":
        api.run["head_sha"] = "f" * 40
    if forgery == "pr":
        api.run["pull_requests"] = [{"number": 99}]
    if forgery == "job-name":
        api.job["name"] = "pretend"
    if forgery == "app":
        api.check["app"]["id"] = 4844131
    if forgery == "pending":
        api.run["status"] = "in_progress"
    if forgery == "failed":
        api.job["conclusion"] = "failure"
    with pytest.raises(p.PolicyError):
        p.validated(api, api.pull)


def test_latest_validation_rerun_overrides_old_green():
    api = FakeAPI()
    old = copy.deepcopy(api.run)
    api.run["id"] = 124
    api.run["conclusion"] = "failure"
    original = api.pages
    api.pages = lambda path, key=None: (
        [api.run, old] if "/runs?" in path else original(path, key)
    )
    with pytest.raises(p.PolicyError):
        p.validated(api, api.pull)


def test_certified_verified_and_receipt_bound(monkeypatch):
    api = FakeAPI()
    monkeypatch.setattr(p, "verify_release", lambda *_: {"asset_size": 4})
    monkeypatch.setattr(p, "download", lambda _: b"test")
    monkeypatch.setattr(p, "verify_wheel", lambda *_: None)
    result = p.evaluate(api, 12)
    assert (
        result["certified"]
        and result["head"] == api.pull["head"]["sha"]
        and result["base"] == api.main()
    )
    assert p.evaluate(api, 12, receipt=result) == result
    result["head"] = "f" * 40
    with pytest.raises(p.PolicyError):
        p.evaluate(api, 12, receipt=result)


def test_main_changed_during_evaluation_fails(monkeypatch):
    api = FakeAPI(manual=True)
    count = 0

    def changing():
        nonlocal count
        count += 1
        return api.pull["base"]["sha"] if count == 1 else "e" * 40

    api.main = changing
    with pytest.raises(p.PolicyError):
        p.evaluate(api, 12)


def test_review_revoked_during_evaluation_fails(monkeypatch):
    api = FakeAPI(manual=True)
    original = api.pages
    count = 0

    def changing(path, key=None):
        nonlocal count
        if "/reviews" in path:
            count += 1
            return [review()] if count == 1 else [review("DISMISSED")]
        return original(path, key)

    api.pages = changing
    with pytest.raises(p.PolicyError):
        p.evaluate(api, 12)


def test_workflow_security_contract():
    path = (
        Path(__file__).resolve().parents[1] / ".github/workflows/publishing-policy.yml"
    )
    assert path.exists(), "trusted-main workflow is missing"
    text = path.read_text()
    assert (
        "pull_request_target:" in text
        and "workflow_dispatch:" in text
        and "schedule:" in text
    )
    assert "pull_request_review:" not in text
    assert "environment: catalogue-policy" in text
    assert "persist-credentials: false" in text
    assert "permission-checks: write" in text
    assert "permission-contents: write" not in text
    assert "CATALOGUE_POLICY_AUTOMERGE_ENABLED" in text
    assert "github.event.pull_request.head" not in text
    import re

    for action in re.findall(r"uses: (\S+)", text):
        assert re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", action), action
