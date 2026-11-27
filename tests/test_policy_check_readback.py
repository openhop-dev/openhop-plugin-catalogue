"""Policy-check publication tolerates bounded lag, never a wrong identity."""

import copy
import json
import time
import urllib.error
from email.message import Message

import pytest
from test_policy_orchestration import FakeAPI
from test_policy_publication import AppAPI
from test_publishing_policy import fixtures, p


class ScriptedAppAPI(AppAPI):
    """Script only the external GET boundary after a real completion PATCH."""

    def __init__(self, readbacks):
        super().__init__()
        self.readbacks = list(readbacks)
        self.patched = False
        self.readback_count = 0

    def repo(self, path, method="GET", data=None):
        result = super().repo(path, method, data)
        if method == "PATCH":
            self.patched = True
        elif method == "GET" and self.patched:
            self.readback_count += 1
            if self.readbacks:
                state = self.readbacks.pop(0)
                if isinstance(state, Exception):
                    raise state
                result.update(copy.deepcopy(state))
        return result


@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize("stale_status", ["in_progress", "completed"])
def test_complete_check_tolerates_delayed_readback(monkeypatch, allowed, stale_status):
    stale_conclusion = (
        None if stale_status == "in_progress" else ("failure" if allowed else "success")
    )
    api = ScriptedAppAPI(
        [
            {"status": stale_status, "conclusion": stale_conclusion},
        ]
    )
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    p.complete_check(api, target, allowed)

    assert api.check["status"] == "completed"
    assert api.check["conclusion"] == ("success" if allowed else "failure")
    assert api.readback_count == 2
    assert sleeps == [1]
    assert len(api.writes) == 2  # One pending POST and one completion PATCH.
    assert api.writes[1][0] == f"/check-runs/{target['check_id']}"


@pytest.mark.parametrize("allowed", [True, False])
def test_readback_exhaustion_is_bounded_and_diagnostic(monkeypatch, capsys, allowed):
    api = ScriptedAppAPI([{"status": "in_progress", "conclusion": None}] * 4)
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    with pytest.raises(p.PolicyError, match="^check readback mismatch$"):
        p.complete_check(api, target, allowed)

    assert api.readback_count == 4
    assert sleeps == [1, 2, 4]
    assert len(api.writes) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        "check_id=1 expected_status=completed expected_conclusion="
        f"{'success' if allowed else 'failure'} "
        "observed_status=in_progress observed_conclusion=None"
    ) in captured.err


@pytest.mark.parametrize(
    "unsafe_state",
    [
        {
            "status": "untrusted-response-marker\nforged",
            "conclusion": ["untrusted-response-marker"],
        },
        {
            "status": {"untrusted-response-marker": "value"},
            "conclusion": "untrusted-response-marker",
        },
    ],
)
def test_mismatch_diagnostics_do_not_echo_untrusted_values(
    monkeypatch, capsys, unsafe_state
):
    api = ScriptedAppAPI([unsafe_state] * 4)
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    with pytest.raises(p.PolicyError, match="^check readback mismatch$"):
        p.complete_check(api, target, True)

    captured = capsys.readouterr()
    assert "untrusted-response-marker" not in captured.out + captured.err
    assert "observed_status=unexpected observed_conclusion=unexpected" in captured.err


@pytest.mark.parametrize("allowed", [True, False])
def test_immediate_readback_does_not_wait(monkeypatch, allowed):
    api = ScriptedAppAPI([])
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    p.complete_check(api, target, allowed)

    assert api.readback_count == 1
    assert sleeps == []
    assert len(api.writes) == 2


def test_readback_can_confirm_on_last_attempt(monkeypatch):
    api = ScriptedAppAPI([{"status": "in_progress", "conclusion": None}] * 3)
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    p.complete_check(api, target, True)

    assert api.readback_count == 4
    assert sleeps == [1, 2, 4]
    assert len(api.writes) == 2


@pytest.mark.parametrize(
    "wrong_identity",
    [
        {"app": {"id": 15368, "slug": "openhop-catalogue-policy"}},
        {"app": {"id": 4844315, "slug": "wrong-app"}},
        {"name": "wrong-check"},
        {"head_sha": "e" * 40},
        {"external_id": "wrong-run"},
    ],
)
@pytest.mark.parametrize("delayed", [False, True])
def test_wrong_identity_is_not_retried(monkeypatch, wrong_identity, delayed):
    states = [{"status": "in_progress", "conclusion": None}] if delayed else []
    api = ScriptedAppAPI(states + [wrong_identity])
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    with pytest.raises(
        p.PolicyError, match="incorrect (policy App identity|check target)"
    ):
        p.complete_check(api, target, True)

    assert api.readback_count == (2 if delayed else 1)
    assert sleeps == ([1] if delayed else [])
    assert len(api.writes) == 2


@pytest.mark.parametrize("status", [401, 403, 429, 500])
@pytest.mark.parametrize("delayed", [False, True])
def test_readback_api_errors_are_not_retried(monkeypatch, status, delayed):
    error = urllib.error.HTTPError(
        "https://api.github.com/check-runs/1",
        status,
        "untrusted-response-marker",
        Message(),
        None,
    )
    states = [{"status": "in_progress", "conclusion": None}] if delayed else []
    api = ScriptedAppAPI(states + [error])
    target = p.create_pending(api, fixtures()[2], "d" * 40)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    with pytest.raises(urllib.error.HTTPError) as raised:
        p.complete_check(api, target, True)

    assert raised.value is error
    assert api.readback_count == (2 if delayed else 1)
    assert sleeps == ([1] if delayed else [])
    assert len(api.writes) == 2


def configure_finalize(monkeypatch, tmp_path, readbacks):
    """Use real evaluation/orchestration with only external API/asset boundaries replaced."""
    api = FakeAPI()
    monkeypatch.setattr(p, "verify_release", lambda *_: {"asset_size": 4})
    monkeypatch.setattr(p, "download", lambda _: b"test")
    monkeypatch.setattr(p, "verify_wheel", lambda *_: None)
    receipt = p.evaluate(api, 12)
    app = ScriptedAppAPI(readbacks)
    target = p.create_pending(app, api.pull, api.main())
    monkeypatch.setattr(p, "API", lambda token=None: api if token is None else app)
    monkeypatch.setenv("GITHUB_REPOSITORY", p.REPOSITORY)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("POLICY_CODE_SHA", api.main())
    monkeypatch.setenv("POLICY_TOKEN", "test-policy")
    monkeypatch.setenv("TARGETS", json.dumps([target]))
    monkeypatch.setenv("RECEIPTS", json.dumps([receipt]))
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    return api, app, receipt, output


def test_finalize_emits_certified_output_after_delayed_confirmation(
    monkeypatch, tmp_path
):
    _, app, receipt, output = configure_finalize(
        monkeypatch, tmp_path, [{"status": "in_progress", "conclusion": None}]
    )

    p.run("finalize")

    assert json.loads(output.read_text().removeprefix("certified=")) == [receipt]
    assert app.check["conclusion"] == "success"
    assert app.readback_count == 2
    assert len(app.writes) == 2


def test_finalize_never_emits_certified_output_after_unconfirmed_write(
    monkeypatch, tmp_path
):
    _, _, _, output = configure_finalize(
        monkeypatch, tmp_path, [{"status": "in_progress", "conclusion": None}] * 4
    )

    with pytest.raises(p.PolicyError, match="^check readback mismatch$"):
        p.run("finalize")

    assert not output.exists()


def test_finalize_rechecks_head_after_delayed_confirmation(monkeypatch, tmp_path):
    api, app, _, output = configure_finalize(
        monkeypatch, tmp_path, [{"status": "in_progress", "conclusion": None}]
    )
    original = api.pr

    def changed(number):
        if app.patched:
            api.pull["head"]["sha"] = "e" * 40
        return original(number)

    monkeypatch.setattr(api, "pr", changed)

    p.run("finalize")

    assert output.read_text() == "certified=[]\n"
    assert app.check["conclusion"] == "failure"
    assert len(app.writes) == 3  # Pending, success, then fail-closed revocation.
