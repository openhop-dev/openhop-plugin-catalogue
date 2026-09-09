# Approved-app publishing policy

The catalogue owns approval. Producers can propose releases, but cannot issue the
required authoritative `publishing-policy` check or approve their own PRs.
The external Worker still publishes metadata from `main`; this workflow does not
upload wheels or deploy the catalogue.

## Decisions

Trusted-main `approved-apps.json` registers `waev.outpost` and `openhop.nomad`.
Both use `openhop-catalogue-publisher[bot]` (user ID `325431437`, publisher App
`4844131`). A PR must be authored by that exact Bot account and originate from
this repository's registered version-specific branch. Only
`catalogue.json` may change, and only that existing entry's `version`,
`source_revision`, `wheel_url`, and `sha256`. Versions must strictly increase;
identity, display metadata, schema, entry order, and all other entries stay unchanged.
Outpost binds `Treehouse-00/waev-outpost-plugin`, distribution `waev-outpost-plugin`,
source `Treehouse-00/pymc_console`, and branch `automation/waev-outpost-v<version>`.
NOMAD binds source and artifact repository `openhop-dev/openhop-nomad-plugin`,
distribution `openhop-nomad-plugin`, and branch `automation/openhop-nomad-v<version>`.
Wheel basenames, package profiles, source verification, and release asset contracts
are explicit registry fields. Unknown plugins are not certified; malformed trusted
registrations fail closed. Other changes require current-head approval by a current
write/maintain/admin human other than the author. Dismissed/stale approvals do not
count; an active maintainer request for changes blocks ordinary approval.
Ordinary changes are never automatically merged by this workflow.

Every decision requires the current trusted schema/validator and the actual
`validate.yml` pull-request run/job from the exact head repository, branch and
SHA. GitHub sometimes returns empty run PR associations; exact source-ref binding
remains required, and a nonempty wrong association is rejected. The head must
contain current `main`. Head, base, validation and ordinary reviews are re-read
before and after check publication; API/configuration failures deny approval.

Certified verification downloads the exact public versioned wheel without an
Authorization header, restricts HTTPS redirects, caps bytes/time/expanded size,
checks SHA-256, release asset identity/size, public tag resolution, wheel RECORD,
distribution/version, profile-specific discovery manifests, and UI entry point.
Outpost retains its root/installed duplicate manifests, UI-only allowlist and exactly
one wheel release asset. NOMAD uses its existing versioned `.data/data/share/openhop/
plugins/openhop.nomad/` installed manifest, default config and three UI assets, plus
`meshcore_nomad_bridge/*.py` and exact dist-info metadata. It has no root manifest.
Its Python runtime must declare `meshcore-nomad-bridge`, whose sole console-script
mapping is `meshcore_nomad_bridge.main:main`. NOMAD releases must contain exactly the
versioned wheel and `openhop-nomad-plugin-v<version>-wheel.zip`; the companion ZIP's
name, URL and bounded size are checked, but its contents are not installed or certified.
NOMAD `source_revision` must equal its resolved public release tag commit (not an
independent source-to-build attestation). No wheel
member is extracted, imported, installed or executed. Public release state is
re-read after verification. GitHub's optional immutable-release flag is not required;
the approved digest pins the bytes clients must accept.

**Private source trust boundary:** `Treehouse-00/pymc_console` is private and
catalogue credentials cannot independently query it. `source_revision` is a
literal SHA asserted by the certified publisher, not independently proven
source-to-build provenance. Public tag/digest/manifest verification does not prove
that the wheel was built from that private source. No App permission expansion or
producer-held approval key is used. Signed build attestations could strengthen this
boundary later but are not part of this change.

## Reusable package profiles

Every registration requires `package_config`. `static-ui-v1` requires `{}` and
retains the root/discovery duplicate manifest and UI-only payload contract.
`python-service-v1` requires exactly these literal fields (NOMAD's registration):

```json
{
  "package_root": "meshcore_nomad_bridge",
  "module": "meshcore_nomad_bridge.main",
  "console_script": "meshcore-nomad-bridge",
  "callable": "main"
}
```

Package root and callable must be ASCII Python identifiers, not keywords. The
module must be one direct child of that package (`<package_root>.<module_name>`),
with an identifier/non-keyword module name. Console commands use lowercase
alphanumeric hyphen-separated segments. Paths, producer-supplied regular expressions,
extra/missing fields and mismatched roots are rejected. These values are read only
from the trusted-main registry, never from the proposed catalogue or wheel.

The Python profile requires `<package_root>/__init__.py`, the configured module's
`.py` file, and allows only direct identifier-named `.py` files in that package.
Nested packages, additional top-level packages and arbitrary package data are not
silently admitted. Its installed data prefix is
`<wheel_basename>-<version>.data/data/share/openhop/plugins/<plugin>/`; the required
files there are `openhop-plugin.json`, `config.default.json`, `ui/index.html`,
`ui/app.js`, and `ui/styles.css`. Runtime must name the registered command; the sole
console-script mapping must be exactly `<console_script> = <module>:<callable>`.
Checks bind metadata and module-file presence without importing code or claiming
the callable was executed. Both profiles retain shared archive safety, size,
SHA-256, exact metadata and complete RECORD verification. Release asset and source
verification contracts remain separate registration fields.

Tests register a synthetic third Python service only in a temporary registry, with
a different package, module, command and callable; production registers only Outpost
and NOMAD. No legacy app-named profile aliases are accepted.

## Onboarding an approved app

1. Inspect the real public release bytes, installed manifest, distribution metadata,
   runtime entrypoint and exact release assets. Do not invent a third registration
   or require a producer packaging migration when an explicit safe profile fits.
2. Add a reviewed `approved-apps.json` registration on catalogue main: bind plugin,
   artifact/source repositories, distribution, wheel basename, branch prefix,
   publisher App/bot IDs and login, package profile and configuration, source verification and asset
   contract. Unknown fields, duplicate identities/repositories/branches and unknown
   profiles are rejected. Registry changes themselves require human approval.
3. Reuse `static-ui-v1` for the UI-only layout or `python-service-v1` for the
   Python-service layout above. Package/module/command names belong in registration,
   not policy code; another app with that layout needs no validator or merge rewrite.
   A different layout requires a separately reviewed validator profile
   with failing-first allowlist/manifest/RECORD/entrypoint attack tests, not a broader
   catch-all allowlist. Keep the four allowed release fields fixed in policy code.
4. Configure the producer to publish final `v<version>` releases, verify downloaded
   bytes, and propose one existing catalogue entry on its registered version branch.
   A first catalogue listing remains a human-approved change. Certified release PRs
   must be ready, current with main, and authored using the registered App installation
   token; Git commit author text is not PR authentication.
5. Run the full tests and validate real public artifacts read-only before review.
   After the registry change is merged, verify the actual policy check, protected
   exact-head merge and separately delivered Worker metadata. Local verification
   is not evidence of a deployed policy or successful automatic merge.

**Shared publisher trust:** the two internal producers intentionally share App
`4844131`. Policy authenticates its Bot account's exact numeric ID/login/type; an
App ID in the registry is administrative identity, not proof of the originating
producer workflow. Anyone holding that shared installation credential can propose
for either registered app using its branch prefix. Repository/artifact/delta checks
constrain the proposal, but do not provide per-producer credential isolation. Do
not extend this shared trust to unrelated external producers without reviewing
separate identities and credential boundaries.

Receipts include the selected plugin alongside exact head/base, catalogue digest
and validation run. Finalize and automatic merging recompute that selection from
trusted policy and current API data; a receipt for one app cannot authorize another.

## Credentials and execution

- Policy App: `openhop-catalogue-policy`, App ID `4844315`, catalogue installation
  only; Checks **write**, Contents **read**, Pull requests **read**. It is separate
  from the publishing App. Bind the required check to this exact integration ID,
  not generic GitHub Actions or just the context name.
- `catalogue-policy` environment secrets must be named exactly
  `OPENHOP_CATALOGUE_POLICY_APP_ID` and
  `OPENHOP_CATALOGUE_POLICY_APP_PRIVATE_KEY`.
- Restrict that environment to **branch** `main` only (not tags), disable admin
  bypass, and do not duplicate its key into repository or producer secrets.
- All checkout refs are explicitly `refs/heads/main`, persisted Git credentials
  are disabled, and current-main code identity is checked at runtime. Actions
  are pinned to full commit SHAs. PR files are fetched as data through the API.
- Prepare and finalize use fresh runners with the policy App. The public wheel
  verifier runs on a different runner without the environment, App key, App token
  or write token. Only bounded JSON job outputs cross this boundary; no artifacts
  or caches from PR workflows are consumed. Finalize re-evaluates those receipts.
- A separate protected job uses `GITHUB_TOKEN` Contents/PR write, not the policy
  App, and runs only when repository variable
  `CATALOGUE_POLICY_AUTOMERGE_ENABLED` is exactly `true`. For a mergeable certified
  PR in `clean` or `unstable` state it requests a protected squash merge with the expected head SHA;
  otherwise it enables native squash auto-merge. It never bypasses protection or
  falls back to a merge after an arbitrary API error. All writes are read back.

Triggers are main-based `pull_request_target`, validation `workflow_run`, main
push, manual dispatch and a 15-minute reconciliation schedule. No
`pull_request_review` workflow executes PR code with secrets. Reconciliation
covers reviews/dismissals, main changes and reruns, including draft transitions.

**Not atomic:** review dismissal and other mutable-state changes can leave an old
successful check until the next run replaces it with pending/failure. Scheduled
Actions may be delayed or disabled; 15 minutes is not a maximum latency guarantee.
Checks bind a head SHA, not an atomic head/base/review snapshot. Final reads narrow
but do not eliminate the race after success. Strict up-to-date branch protection
is mandatory for base races; automatic merge enablement itself has no expected-head
parameter. Treat these limits as activation review items, not solved revocation.

## Operational protection checklist

This is a maintenance/bootstrap checklist, not a claim that the existing Outpost
pipeline is still staged or disabled. The registry extension must be merged through
normal review before trusted-main execution can use it. Local tests do not activate
it; no settings change or privileged dispatch is needed for local development.

1. Merge policy/registry changes through the existing required checks and human
   approval path. Do not weaken protection or change activation settings merely
   to onboard another app. For a fresh installation keep automatic merging disabled
   until the required policy check and credentials are verified.
2. Verify installation, exact App permissions and both environment secret names.
   Confirm administrator bypass is disabled and branch-only main restrictions
   are enforced before relying on the key boundary. Reinspect live settings;
   historical observations are not evidence of current configuration.
3. Exercise the workflow on main and real PRs: certified success, ordinary missing
   and current approval, stale/dismissed approval, forbidden metadata/workflow
   changes, wrong publisher/fork, artifact mismatch, API failure and head/base
   movement. Verify issuing App ID `4844315` and pending/failure replacement.
4. Review the revocation propagation window above. Confirm strict up-to-date
   required validation, no bypass for the merge identity, squash and native
   auto-merge repository support. Then require `publishing-policy` bound to App
   `4844315` alongside `validate`. Only a deliberate, tested cutover may replace
   the blanket one-review requirement with this conditional policy; native one
   review otherwise intentionally continues to block unreviewed certified merges.
5. Only after real gate/merge-path verification set the activation variable to
   `true`. Check the exact merged head and separately verify the public Worker
   catalogue. Roll back by disabling the variable and restoring native human
   review; never remove validation or leave a standing bypass.

Local tests and actionlint do not prove the live App installation, protected
workflow dispatch, or merge path. During implementation the real public
`v0.9.379` artifact passed release/digest/manifest/RECORD verification (12,196,975
bytes); API metadata required authenticated read-only `gh api` after anonymous
rate limiting, while wheel download remained unauthenticated. Historical PR 11
validated the run/job raw-head SHA behavior and empty PR-association handling.
No live approval check or automatic merge was issued by local verification.
