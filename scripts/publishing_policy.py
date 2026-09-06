#!/usr/bin/env python3
"""Trusted-main publishing policy. PR files and wheel members are data only."""

from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import json
import os
import re
import signal
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "openhop-dev/openhop-plugin-catalogue"
POLICY_APP_ID = 4844315
POLICY_APP_SLUG = "openhop-catalogue-policy"
CHECK = "publishing-policy"
CERTIFICATION = {
    "plugin": "waev.outpost",
    "artifact_repository": "Treehouse-00/waev-outpost-plugin",
    "source_repository": "Treehouse-00/pymc_console",
    "distribution": "waev-outpost-plugin",
    "publisher_app_id": 4844131,
    "publisher_login": "openhop-catalogue-publisher[bot]",
    "publisher_user_id": 325431437,
    "branch_prefix": "automation/waev-outpost-v",
    "fields": frozenset({"version", "source_revision", "wheel_url", "sha256"}),
}
SHA = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
MAX_JSON = 4 * 1024 * 1024
MAX_WHEEL = 64 * 1024 * 1024


class PolicyError(RuntimeError):
    """Fail closed; never print network bodies, credentials or PR-controlled text."""


def require(condition, message="policy condition not satisfied"):
    if not condition:
        raise PolicyError(message)


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=pairs)


def certified_entry(pr, files, base, candidate):
    """A mismatch is an ordinary PR, never implicit certification."""
    try:
        c = CERTIFICATION
        require(files == ["catalogue.json"])
        require(
            pr["user"]
            == {
                **pr["user"],
                "id": c["publisher_user_id"],
                "login": c["publisher_login"],
                "type": "Bot",
            }
        )
        require(pr["head"]["repo"]["full_name"] == REPOSITORY)
        require(
            pr["base"]["repo"]["full_name"] == REPOSITORY
            and pr["base"]["ref"] == "main"
        )
        require(base["schema"] == candidate["schema"] == 2)
        old = [x for x in base["plugins"] if x["id"] == c["plugin"]]
        new = [x for x in candidate["plugins"] if x["id"] == c["plugin"]]
        require(len(old) == len(new) == 1)
        old, new = old[0], new[0]
        require(set(old) == set(new))
        require(
            new["repository"] == c["artifact_repository"]
            and new["distribution"] == c["distribution"]
        )
        require(VERSION.fullmatch(new["version"]) and VERSION.fullmatch(old["version"]))
        require(
            tuple(map(int, new["version"].split(".")))
            > tuple(map(int, old["version"].split(".")))
        )
        require(pr["head"]["ref"] == c["branch_prefix"] + new["version"])
        require(
            SHA.fullmatch(new["source_revision"])
            and re.fullmatch(r"[0-9a-f]{64}", new["sha256"])
        )
        require(new["wheel_url"] == wheel_url(new["version"]))
        restored = copy.deepcopy(candidate)
        replacement = next(x for x in restored["plugins"] if x["id"] == c["plugin"])
        for field in c["fields"]:
            replacement[field] = old[field]
        require(restored == base)
        return new
    except (PolicyError, KeyError, TypeError, ValueError):
        return None


def wheel_url(version):
    require(isinstance(version, str) and VERSION.fullmatch(version), "invalid version")
    return (
        f"https://github.com/{CERTIFICATION['artifact_repository']}/releases/download/"
        f"v{version}/waev_outpost_plugin-{version}-py3-none-any.whl"
    )


def approved(pr, reviews, permission):
    latest = {}
    for r in sorted(reviews, key=lambda x: x["id"]):
        user = r["user"]
        if user["type"] != "User" or user["id"] == pr["user"]["id"]:
            continue
        if r["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest[user["id"]] = r
    active = [
        r
        for r in latest.values()
        if permission(r["user"]["login"]) in {"write", "maintain", "admin"}
    ]
    if any(r["state"] == "CHANGES_REQUESTED" for r in active):
        return False
    return any(
        r["state"] == "APPROVED" and r["commit_id"] == pr["head"]["sha"] for r in active
    )


def assert_fresh(before, now, main):
    require(now["state"] == "open" and not now["draft"], "PR not open and ready")
    require(
        now["base"]["ref"] == "main" and now["base"]["repo"]["full_name"] == REPOSITORY,
        "wrong base",
    )
    require(
        now["head"] == before["head"]
        and now["base"] == before["base"]
        and now["user"] == before["user"],
        "PR changed during evaluation",
    )
    require(
        SHA.fullmatch(main) and now["base"]["sha"] == main,
        "main changed during evaluation",
    )
    require(SHA.fullmatch(now["head"]["sha"]), "invalid head SHA")


@contextlib.contextmanager
def deadline(seconds=60):
    """Linux main thread: hard wall deadline includes DNS/headers/redirects/body."""

    def expired(*_):
        raise PolicyError("network deadline exceeded")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def bounded_read(response, limit):
    data = bytearray()
    read = getattr(response, "read1", response.read)
    while True:
        chunk = read(min(65536, limit + 1 - len(data)))
        if not chunk:
            require(not getattr(response, "length", 0), "truncated response")
            break
        data.extend(chunk)
        require(len(data) <= limit, "response too large")
    length = response.headers.get("Content-Length")
    require(length is None or int(length) == len(data), "response length mismatch")
    return bytes(data)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PolicyError("API redirect refused")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_download_url(url):
    parsed = urllib.parse.urlsplit(url)
    require(
        parsed.scheme == "https"
        and parsed.netloc
        in {
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }
        and not parsed.fragment,
        "unsafe download origin",
    )


def download(url):
    check_download_url(url)
    # Deliberately separate from API(): no authentication on any download hop.
    request = urllib.request.Request(
        url, headers={"User-Agent": "openhop-catalogue-policy"}
    )
    with (
        deadline(),
        urllib.request.build_opener(SafeRedirect()).open(
            request, timeout=15
        ) as response,
    ):
        return bounded_read(response, MAX_WHEEL)


class API:
    def __init__(self, token=None):
        self.token = token if token is not None else os.environ.get("GH_TOKEN", "")
        require(bool(self.token), "GH_TOKEN missing")

    def call(self, path, method="GET", data=None):
        require(
            path.startswith("/") and not path.startswith("//") and "\n" not in path,
            "invalid API path",
        )
        request = urllib.request.Request(
            "https://api.github.com" + path,
            data=None if data is None else json.dumps(data).encode(),
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": CHECK,
                "Content-Type": "application/json",
            },
        )
        with (
            deadline(),
            urllib.request.build_opener(NoRedirect()).open(
                request, timeout=15
            ) as response,
        ):
            raw = bounded_read(response, MAX_JSON)
        return strict_json(raw) if raw else None

    def pages(self, path, key=None):
        result = []
        for page in range(1, 11):
            value = self.call(
                path + ("&" if "?" in path else "?") + f"per_page=100&page={page}"
            )
            rows = value[key] if key else value
            require(isinstance(rows, list), "invalid pagination response")
            result.extend(rows)
            if len(rows) < 100:
                if key and "total_count" in value:
                    require(
                        len(result) == value["total_count"],
                        "incomplete API enumeration",
                    )
                return result
        raise PolicyError("pagination limit exceeded")

    def repo(self, path, **kwargs):
        return self.call("/repos/" + REPOSITORY + path, **kwargs)

    def main(self):
        return self.repo("/git/ref/heads/main")["object"]["sha"]

    def pr(self, number):
        require(type(number) is int and number > 0, "invalid PR number")
        return self.repo(f"/pulls/{number}")

    def catalogue(self, sha):
        require(SHA.fullmatch(sha), "invalid revision")
        blob = self.repo(f"/contents/catalogue.json?ref={sha}")
        require(
            blob["type"] == "file" and blob["encoding"] == "base64",
            "catalogue must be a regular file",
        )
        return strict_json(base64.b64decode(blob["content"]))


MAX_UNPACKED = 256 * 1024 * 1024


def verify_wheel(raw, item):
    """Adapted from producer update_plugin_catalogue.py; never extract or execute."""
    import csv
    import io
    import stat
    import zipfile
    from email.parser import BytesParser
    from email.policy import default
    from pathlib import PurePosixPath

    require(
        len(raw) <= MAX_WHEEL and hashlib.sha256(raw).hexdigest() == item["sha256"],
        "wheel digest mismatch",
    )
    version = item["version"]
    require(VERSION.fullmatch(version), "invalid wheel version")
    prefix = f"waev_outpost_plugin-{version}.dist-info/"
    record = prefix + "RECORD"
    meta = prefix + "METADATA"
    manifest_path = "share/openhop/plugins/waev.outpost/openhop-plugin.json"
    required = {meta, record, "openhop-plugin.json", manifest_path, "ui/index.html"}
    allowed = required | {prefix + "WHEEL", prefix + "top_level.txt"}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [x.filename for x in infos]
        require(
            len(names) <= 10000 and len(names) == len(set(names)),
            "duplicate or excessive wheel members",
        )
        require(
            sum(x.file_size for x in infos) <= MAX_UNPACKED, "expanded wheel too large"
        )
        require(required <= set(names), "required wheel member missing")
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            require(
                not path.is_absolute()
                and str(path) == name
                and ".." not in path.parts
                and "\\" not in name
                and not stat.S_ISLNK(info.external_attr >> 16)
                and not info.flag_bits & 1
                and not info.is_dir(),
                "unsafe wheel member",
            )
            require(
                name in allowed or name.startswith("ui/"), "unexpected wheel member"
            )
        rows = csv.reader(io.StringIO(archive.read(record).decode("utf-8")))
        seen = set()
        for row in rows:
            require(len(row) == 3, "invalid RECORD row")
            name, digest, size = row
            require(
                name in names and name not in seen, "duplicate or unknown RECORD member"
            )
            seen.add(name)
            if name == record:
                require(digest == size == "", "invalid RECORD self entry")
            else:
                payload = archive.read(name)
                actual = (
                    base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
                    .decode()
                    .rstrip("=")
                )
                require(
                    digest == "sha256=" + actual and size == str(len(payload)),
                    "RECORD mismatch",
                )
        require(seen == set(names), "RECORD coverage incomplete")
        manifest_raw = archive.read("openhop-plugin.json")
        require(
            manifest_raw == archive.read(manifest_path), "discovery manifest mismatch"
        )
        manifest = strict_json(manifest_raw)
        require(
            manifest.get("schema") == 1
            and manifest.get("id") == CERTIFICATION["plugin"]
            and manifest.get("version") == version,
            "manifest identity mismatch",
        )
        require(
            manifest.get("ui", {}).get("type") == "application"
            and manifest["ui"].get("entry") == "ui/index.html",
            "manifest entrypoint mismatch",
        )
        metadata = BytesParser(policy=default).parsebytes(archive.read(meta))
        require(
            metadata.get_all("Name") == [CERTIFICATION["distribution"]]
            and metadata.get_all("Version") == [version],
            "distribution metadata mismatch",
        )


def resolve_tag(api, repository, tag):
    require(
        repository
        in {CERTIFICATION["artifact_repository"], CERTIFICATION["source_repository"]},
        "unapproved repository",
    )
    require(re.fullmatch(r"v" + VERSION.pattern, tag), "invalid tag")
    obj = api.call(f"/repos/{repository}/git/ref/tags/{tag}")["object"]
    for _ in range(5):
        require(SHA.fullmatch(obj["sha"]), "invalid tag revision")
        if obj["type"] == "commit":
            return obj["sha"]
        require(obj["type"] == "tag", "tag does not resolve to commit")
        obj = api.call(f"/repos/{repository}/git/tags/{obj['sha']}")["object"]
    raise PolicyError("tag nesting limit exceeded")


def verify_release(api, item):
    version = item["version"]
    require(item["wheel_url"] == wheel_url(version), "release URL mismatch")
    repo = CERTIFICATION["artifact_repository"]
    release = api.call(f"/repos/{repo}/releases/tags/v{version}")
    require(
        release["tag_name"] == "v" + version
        and not release["draft"]
        and not release["prerelease"],
        "release not final",
    )
    assets = release["assets"]
    require(len(assets) == 1, "release must contain exactly one wheel")
    asset = assets[0]
    require(
        asset["name"] == item["wheel_url"].rsplit("/", 1)[1]
        and asset["browser_download_url"] == item["wheel_url"]
        and 0 < asset["size"] <= MAX_WHEEL,
        "release asset mismatch",
    )
    artifact_sha = resolve_tag(api, repo, "v" + version)
    # The certified publisher asserts this private source revision. Catalogue-only
    # credentials cannot independently verify pymc_console; public artifact checks
    # below do not claim source-to-build provenance.
    source_sha = item["source_revision"]
    require(
        isinstance(source_sha, str) and SHA.fullmatch(source_sha),
        "invalid source revision",
    )
    return {
        "artifact_sha": artifact_sha,
        "source_sha": source_sha,
        "asset_size": asset["size"],
    }


def validated(api, pr):
    """Require the actual validate workflow run/job, not a reusable context name."""
    workflow = api.repo("/actions/workflows/validate.yml")
    require(
        workflow["path"] == ".github/workflows/validate.yml",
        "validation workflow mismatch",
    )
    runs = api.pages(
        f"/repos/{REPOSITORY}/actions/workflows/{workflow['id']}/runs?event=pull_request&head_sha={pr['head']['sha']}",
        "workflow_runs",
    )
    runs = [
        r
        for r in runs
        if r["workflow_id"] == workflow["id"]
        and r["head_sha"] == pr["head"]["sha"]
        and r["event"] == "pull_request"
        and r["path"] == ".github/workflows/validate.yml"
        and r["head_repository"]["full_name"] == pr["head"]["repo"]["full_name"]
        and r["head_branch"] == pr["head"]["ref"]
        and (
            not r["pull_requests"]
            or any(x["number"] == pr["number"] for x in r["pull_requests"])
        )
    ]
    require(bool(runs), "trusted validation run missing")
    run = max(runs, key=lambda r: r["id"])
    require(
        run["status"] == "completed" and run["conclusion"] == "success",
        "validation not successful",
    )
    jobs = api.pages(
        f"/repos/{REPOSITORY}/actions/runs/{run['id']}/jobs?filter=latest", "jobs"
    )
    jobs = [j for j in jobs if j["name"] == "validate"]
    require(
        len(jobs) == 1
        and jobs[0]["status"] == "completed"
        and jobs[0]["conclusion"] == "success",
        "validate job not successful",
    )
    prefix = f"https://api.github.com/repos/{REPOSITORY}/check-runs/"
    url = jobs[0]["check_run_url"]
    require(
        url.startswith(prefix) and url[len(prefix) :].isdigit(),
        "invalid validate check link",
    )
    check = api.repo("/check-runs/" + url[len(prefix) :])
    require(
        check["app"]["id"] == 15368
        and check["head_sha"] == pr["head"]["sha"]
        and check["name"] == "validate"
        and check["status"] == "completed"
        and check["conclusion"] == "success",
        "validate check identity mismatch",
    )
    return run["id"]


def current_approval(api, pr):
    reviews = api.pages(f"/repos/{REPOSITORY}/pulls/{pr['number']}/reviews")

    def permission(login):
        require(re.fullmatch(r"[A-Za-z0-9-]{1,39}", login), "invalid reviewer login")
        return api.repo(f"/collaborators/{login}/permission")["permission"]

    return approved(pr, reviews, permission)


def validate_data(candidate, files):
    # Always use main's schema and validator, never scripts or schema from the PR.
    import tempfile
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "trusted_catalogue_validator", ROOT / "scripts/validate_catalogue.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    require(
        not any(f["filename"].lower().endswith(".whl") for f in files),
        "wheel committed to metadata repository",
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "schema").mkdir()
        (root / "schema/catalogue.schema.json").write_bytes(
            (ROOT / "schema/catalogue.schema.json").read_bytes()
        )
        (root / "catalogue.json").write_text(json.dumps(candidate), encoding="utf-8")
        validator.validate_catalogue(root)


def evaluate(api, number, receipt=None):
    pr = api.pr(number)
    main = api.main()
    assert_fresh(pr, pr, main)
    compare = api.repo(f"/compare/{main}...{pr['head']['sha']}")
    require(
        compare["merge_base_commit"]["sha"] == main, "PR must be up to date with main"
    )
    files = api.pages(f"/repos/{REPOSITORY}/pulls/{number}/files")
    if "changed_files" in pr:
        require(len(files) == pr["changed_files"], "incomplete PR diff")
    tree = api.repo(f"/git/trees/{pr['head']['sha']}")
    entries = [x for x in tree["tree"] if x["path"] == "catalogue.json"]
    require(
        not tree.get("truncated")
        and len(entries) == 1
        and entries[0]["mode"] == "100644"
        and entries[0]["type"] == "blob",
        "catalogue not a regular file",
    )
    candidate = api.catalogue(pr["head"]["sha"])
    base = api.catalogue(main)
    validate_data(candidate, files)
    validation = validated(api, pr)
    item = certified_entry(pr, [f["filename"] for f in files], base, candidate)
    if item and any(f["status"] != "modified" for f in files):
        item = None
    result = {
        "number": number,
        "head": pr["head"]["sha"],
        "base": main,
        "catalogue_digest": hashlib.sha256(
            json.dumps(candidate, sort_keys=True).encode()
        ).hexdigest(),
        "validation_run": validation,
        "allowed": True,
        "certified": item is not None,
    }
    if item:
        if receipt is None:
            release = verify_release(api, item)
            raw = download(item["wheel_url"])
            require(len(raw) == release["asset_size"], "release size mismatch")
            verify_wheel(raw, item)
            require(
                verify_release(api, item) == release,
                "release changed during verification",
            )
        else:
            # Only a needs.verify output of this trusted workflow can supply this.
            require(
                receipt == result, "verification receipt no longer matches API state"
            )
    else:
        require(current_approval(api, pr), "current maintainer approval required")
    # Re-read decision-relevant mutable state after expensive work.
    require(validated(api, pr) == validation, "validation changed during evaluation")
    if not item:
        require(current_approval(api, pr), "maintainer approval revoked")
    assert_fresh(pr, api.pr(number), api.main())
    return result


def trusted_context(api):
    require(
        os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "wrong execution repository"
    )
    require(
        os.environ.get("GITHUB_REF") == "refs/heads/main", "policy must run on main"
    )
    code = os.environ.get("POLICY_CODE_SHA", "")
    require(
        SHA.fullmatch(code) and api.main() == code, "trusted code is not current main"
    )
    return code


def check_identity(check, target):
    require(
        check["app"]["id"] == POLICY_APP_ID and check["app"]["slug"] == POLICY_APP_SLUG,
        "incorrect policy App identity",
    )
    require(
        check["name"] == CHECK
        and check["head_sha"] == target["head"]
        and check["external_id"] == target["external_id"],
        "incorrect check target",
    )


def create_pending(app, pr, main):
    require(
        SHA.fullmatch(pr["head"]["sha"]) and SHA.fullmatch(main),
        "invalid check revisions",
    )
    target = {
        "number": pr["number"],
        "head": pr["head"]["sha"],
        "base": main,
        "external_id": f"{main}:{os.environ.get('GITHUB_RUN_ID', 'local')}:{pr['number']}",
    }
    created = app.repo(
        "/check-runs",
        method="POST",
        data={
            "name": CHECK,
            "head_sha": target["head"],
            "status": "in_progress",
            "external_id": target["external_id"],
            "output": {
                "title": "Evaluating publishing policy",
                "summary": "Trusted-main reconciliation in progress.",
            },
        },
    )
    target["check_id"] = created["id"]
    check_identity(app.repo(f"/check-runs/{target['check_id']}"), target)
    return target


def complete_check(app, target, allowed):
    path = f"/check-runs/{target['check_id']}"
    check_identity(app.repo(path), target)
    conclusion = "success" if allowed else "failure"
    app.repo(
        path,
        method="PATCH",
        data={
            "status": "completed",
            "conclusion": conclusion,
            "output": {
                "title": "Publishing policy "
                + ("satisfied" if allowed else "not satisfied"),
                "summary": "Current-head validation and conditional approval evaluated on trusted main. See the policy workflow logs; API failures deny approval.",
            },
        },
    )
    check = app.repo(path)
    check_identity(check, target)
    require(
        check["status"] == "completed" and check["conclusion"] == conclusion,
        "check readback mismatch",
    )


def enable_auto(api, receipt, target):
    require(
        os.environ.get("CATALOGUE_POLICY_AUTOMERGE_ENABLED") == "true",
        "automatic merge not activated",
    )
    require(
        receipt.get("certified") is True,
        "ordinary PR must not be automatically enabled",
    )
    trusted_context(api)
    require(
        evaluate(api, receipt["number"], receipt=receipt) == receipt,
        "auto-enable decision changed",
    )
    check = api.repo(f"/check-runs/{target['check_id']}")
    check_identity(check, target)
    require(
        check["status"] == "completed" and check["conclusion"] == "success",
        "policy check not successful",
    )
    pr = api.pr(receipt["number"])
    require(
        pr["head"]["sha"] == receipt["head"] and api.main() == receipt["base"],
        "auto-enable refs changed",
    )
    # Optional running/failed checks (including this job) can make an otherwise
    # eligible PR "unstable". Auto-merge enrollment may reject such a PR as
    # immediately mergeable. Let the protected endpoint enforce required checks
    # for either state, using the exact head and non-bypass GITHUB_TOKEN.
    # Never fall back after a rejected merge or an arbitrary API error.
    if pr.get("mergeable") is True and pr.get("mergeable_state") in {
        "clean",
        "unstable",
    }:
        result = api.repo(
            f"/pulls/{receipt['number']}/merge",
            method="PUT",
            data={"sha": receipt["head"], "merge_method": "squash"},
        )
        require(result.get("merged") is True, "protected merge rejected")
        now = api.pr(receipt["number"])
        require(
            now.get("merged") is True and now["head"]["sha"] == receipt["head"],
            "exact-head merge not confirmed",
        )
        return
    # Auto-enable has no expectedHeadOid parameter. Required checks and strict
    # up-to-date protection, not this request, enforce the eventual merge.
    result = api.call(
        "/graphql",
        method="POST",
        data={
            "query": "mutation($id:ID!){enablePullRequestAutoMerge(input:{pullRequestId:$id,mergeMethod:SQUASH}){pullRequest{id}}}",
            "variables": {"id": pr["node_id"]},
        },
    )
    require(not result.get("errors"), "auto-enable mutation failed")
    now = api.pr(receipt["number"])
    require(
        now.get("auto_merge") is not None or now.get("merged") is True,
        "auto-enable not confirmed",
    )


def output(name, value):
    serialized = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    require(len(serialized) < 200000, "job output too large")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(name + "=" + serialized + "\n")


def run(mode):
    api = API()
    main = trusted_context(api)
    if mode == "prepare":
        app = API(os.environ.get("POLICY_TOKEN", ""))
        prs = api.pages(f"/repos/{REPOSITORY}/pulls?state=open&base=main")
        require(len(prs) <= 50, "more than 50 open PRs; manual intervention required")
        targets = []
        for row in prs:
            pr = api.pr(row["number"])
            # Include drafts: replace any old green with an in-progress/failure.
            targets.append(create_pending(app, pr, main))
        output("targets", targets)
        return
    targets = strict_json(os.environ.get("TARGETS", "[]"))
    require(isinstance(targets, list) and len(targets) <= 50, "invalid targets")
    if mode == "verify":
        receipts = []
        for target in targets:
            try:
                trusted_context(api)
                receipt = evaluate(api, target["number"])
                require(
                    receipt["head"] == target["head"]
                    and receipt["base"] == target["base"],
                    "prepared refs changed",
                )
                receipts.append(receipt)
            except Exception as exc:
                # Exception text may contain attacker data, signed URLs or secrets.
                print(f"PR #{int(target['number'])}: denied ({type(exc).__name__})")
        output("receipts", receipts)
        return
    receipts = strict_json(os.environ.get("RECEIPTS", "[]"))
    by_number = {r["number"]: r for r in receipts}
    if mode == "finalize":
        app = API(os.environ.get("POLICY_TOKEN", ""))
        successful = []
        for target in targets:
            allowed = False
            try:
                trusted_context(api)
                receipt = by_number[target["number"]]
                require(
                    receipt["head"] == target["head"]
                    and receipt["base"] == target["base"],
                    "prepared refs changed",
                )
                evaluate(api, target["number"], receipt=receipt)
                allowed = True
            except Exception as exc:
                print(f"PR #{int(target['number'])}: denied ({type(exc).__name__})")
            complete_check(app, target, allowed)
            # Post-write fresh read; revoke if API/ref/review changes are observed.
            if allowed:
                try:
                    trusted_context(api)
                    evaluate(api, target["number"], receipt=receipt)
                except Exception:
                    complete_check(app, target, False)
                    continue
                if receipt["certified"]:
                    successful.append(receipt)
        output("certified", successful)
        return
    require(mode == "auto", "unknown policy command")
    for target in targets:
        if target["number"] in by_number:
            enable_auto(api, by_number[target["number"]], target)


def main():
    try:
        require(
            len(sys.argv) == 2
            and sys.argv[1] in {"prepare", "verify", "finalize", "auto"},
            "expected policy mode",
        )
        run(sys.argv[1])
        return 0
    except PolicyError as exc:
        # PolicyError messages are trusted-code literals, never API response text.
        print(f"Publishing policy failed closed (PolicyError): {exc}.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"Publishing policy failed closed ({type(exc).__name__}).", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
