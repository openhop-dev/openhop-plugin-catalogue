"""Regression coverage for observed GitHub API and isolated job boundaries."""

import copy
from pathlib import Path

import pytest
from test_publishing_policy import p, fixtures
from test_policy_orchestration import FakeAPI


def test_empty_run_associations_use_exact_source_ref():
    api = FakeAPI()
    api.run["pull_requests"] = []
    assert p.validated(api, api.pull) == 123


@pytest.mark.parametrize("field", ["head_branch", "head_repository"])
def test_empty_associations_do_not_allow_wrong_source(field):
    api = FakeAPI()
    api.run["pull_requests"] = []
    api.run[field] = "wrong" if field == "head_branch" else {"full_name": "evil/fork"}
    with pytest.raises(p.PolicyError):
        p.validated(api, api.pull)


@pytest.mark.parametrize("clean", [True, False])
def test_certified_auto_success_paths(monkeypatch, clean):
    monkeypatch.setenv("CATALOGUE_POLICY_AUTOMERGE_ENABLED", "true")
    monkeypatch.setattr(p, "trusted_context", lambda _: "d" * 40)
    receipt = {"certified": True, "number": 12, "head": "c" * 40, "base": "d" * 40}
    monkeypatch.setattr(p, "evaluate", lambda *a, **k: receipt)
    target = {"head": "c" * 40, "external_id": "test", "check_id": 1}

    class MergeAPI:
        def __init__(self):
            self.pull = fixtures()[2]
            self.pull.update(
                node_id="PR_test",
                mergeable=clean,
                mergeable_state="clean" if clean else "blocked",
            )
            self.writes = []

        def main(self):
            return "d" * 40

        def pr(self, number):
            return copy.deepcopy(self.pull)

        def repo(self, path, method="GET", data=None):
            if method == "PUT":
                assert path == "/pulls/12/merge"
                assert data == {"sha": "c" * 40, "merge_method": "squash"}
                self.writes.append(data)
                self.pull["merged"] = True
                return {"merged": True}
            return {
                "app": {"id": 4844315, "slug": "openhop-catalogue-policy"},
                "name": p.CHECK,
                "head_sha": "c" * 40,
                "external_id": "test",
                "status": "completed",
                "conclusion": "success",
            }

        def call(self, path, method="GET", data=None):
            assert path == "/graphql" and method == "POST"
            assert "enablePullRequestAutoMerge" in data["query"]
            self.writes.append(data)
            self.pull["auto_merge"] = {"merge_method": "squash"}
            return {"data": {}}

    api = MergeAPI()
    p.enable_auto(api, receipt, target)
    assert len(api.writes) == 1


def test_artifact_runner_has_no_policy_key_or_write_permissions():
    text = (
        Path(__file__).resolve().parents[1] / ".github/workflows/publishing-policy.yml"
    ).read_text()
    verify = text.split("  verify:\n", 1)[1].split("  finalize:\n", 1)[0]
    assert "secrets." not in verify and "environment:" not in verify
    assert ": write" not in verify and "create-github-app-token" not in verify
    assert "ref: refs/heads/main" in verify
    assert text.count("secrets.OPENHOP_CATALOGUE_POLICY_APP_ID") == 2
    assert text.count("secrets.OPENHOP_CATALOGUE_POLICY_APP_PRIVATE_KEY") == 2
    assert "secrets.OPENHOP_CATALOGUE_POLICY_PRIVATE_KEY" not in text
