"""Protected merge regression: optional checks do not define merge eligibility."""

import copy
import pytest
from test_publishing_policy import p


class MergeAPI:
    def __init__(self, state="unstable", reject=False):
        self.pull = {
            "number": 15,
            "node_id": "PR_test",
            "head": {"sha": "a" * 40},
            "mergeable": True,
            "mergeable_state": state,
            "merged": False,
        }
        self.writes = []
        self.reject = reject

    def main(self):
        return "b" * 40

    def pr(self, number):
        return copy.deepcopy(self.pull)

    def repo(self, path, method="GET", data=None):
        if path == "/check-runs/1":
            return {
                "app": {"id": p.POLICY_APP_ID, "slug": p.POLICY_APP_SLUG},
                "name": p.CHECK,
                "head_sha": "a" * 40,
                "external_id": "test",
                "status": "completed",
                "conclusion": "success",
            }
        assert path == "/pulls/15/merge" and method == "PUT"
        self.writes.append((path, data))
        if self.reject:
            return {"merged": False}
        self.pull["merged"] = True
        return {"merged": True}

    def call(self, path, method="GET", data=None):
        self.writes.append((path, data))
        return {"errors": [{"type": "UNPROCESSABLE", "message": "untrusted response"}]}


def setup_auto(monkeypatch):
    monkeypatch.setenv("CATALOGUE_POLICY_AUTOMERGE_ENABLED", "true")
    monkeypatch.setattr(p, "trusted_context", lambda api: api.main())
    receipt = {"number": 15, "certified": True, "head": "a" * 40, "base": "b" * 40}
    monkeypatch.setattr(p, "evaluate", lambda api, number, receipt: receipt)
    target = {"check_id": 1, "head": "a" * 40, "external_id": "test"}
    return receipt, target


@pytest.mark.parametrize("state", ["clean", "unstable"])
def test_certified_mergeable_pr_uses_exact_head_protected_merge(monkeypatch, state):
    receipt, target = setup_auto(monkeypatch)
    api = MergeAPI(state)
    p.enable_auto(api, receipt, target)
    assert api.writes == [
        ("/pulls/15/merge", {"sha": "a" * 40, "merge_method": "squash"})
    ]
    assert api.pull["merged"]


def test_protected_merge_rejection_does_not_fall_back(monkeypatch):
    receipt, target = setup_auto(monkeypatch)
    api = MergeAPI(reject=True)
    with pytest.raises(p.PolicyError, match="protected merge rejected"):
        p.enable_auto(api, receipt, target)
    assert len(api.writes) == 1 and api.writes[0][0] == "/pulls/15/merge"


def test_changed_head_prevents_merge(monkeypatch):
    receipt, target = setup_auto(monkeypatch)
    api = MergeAPI()
    api.pull["head"]["sha"] = "c" * 40
    with pytest.raises(p.PolicyError, match="refs changed"):
        p.enable_auto(api, receipt, target)
    assert not api.writes


@pytest.mark.parametrize("state", ["blocked", "behind", "dirty", "unknown"])
def test_other_states_never_attempt_direct_merge(monkeypatch, state):
    receipt, target = setup_auto(monkeypatch)
    api = MergeAPI(state)
    with pytest.raises(p.PolicyError, match="auto-enable mutation failed"):
        p.enable_auto(api, receipt, target)
    assert api.writes[0][0] == "/graphql"


def test_unconfirmed_merge_readback_fails(monkeypatch):
    receipt, target = setup_auto(monkeypatch)
    api = MergeAPI()
    original = api.pr

    def stale(number):
        result = original(number)
        result["merged"] = False
        return result

    api.pr = stale
    with pytest.raises(p.PolicyError, match="exact-head merge not confirmed"):
        p.enable_auto(api, receipt, target)


def test_policy_reasons_are_trusted_literals():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(p.__file__).read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == "require" and len(node.args) > 1:
            assert isinstance(node.args[1], ast.Constant)
        if node.func.id == "PolicyError":
            assert isinstance(node.args[0], ast.Constant) or (
                isinstance(node.args[0], ast.Name) and node.args[0].id == "message"
            )


def test_untrusted_exception_text_is_not_logged(monkeypatch, capsys):
    monkeypatch.setattr(p.sys, "argv", ["publishing_policy.py", "auto"])

    def fail(mode):
        raise ValueError("SECRET_RESPONSE")

    monkeypatch.setattr(p, "run", fail)
    assert p.main() == 1
    assert "SECRET_RESPONSE" not in capsys.readouterr().err


def test_cli_reports_safe_policy_reason(monkeypatch, capsys):
    monkeypatch.setattr(p.sys, "argv", ["publishing_policy.py", "auto"])

    def fail(mode):
        raise p.PolicyError("auto-enable mutation failed")

    monkeypatch.setattr(p, "run", fail)
    assert p.main() == 1
    assert "auto-enable mutation failed" in capsys.readouterr().err
