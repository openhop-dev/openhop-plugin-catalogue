# Certified publishing policy (staged, not activated)

The catalogue owns approval. Producers can propose releases, but cannot issue the
required authoritative `publishing-policy` check or approve their own PRs.
The external Worker still publishes metadata from `main`; this workflow does not
upload wheels or deploy the catalogue.

## Decisions

Only `waev.outpost` is certified. Its PR must be authored by
`openhop-catalogue-publisher[bot]` (user ID `325431437`, publisher App `4844131`),
from this repository's `automation/waev-outpost-v<version>` branch. Only
`catalogue.json` may change, and only that existing entry's `version`,
`source_revision`, `wheel_url`, and `sha256`. Versions must strictly increase;
identity, display metadata, schema, entry order, and all other entries stay unchanged.
The artifact repository is `Treehouse-00/waev-outpost-plugin`, distribution
`waev-outpost-plugin`. Other changes require current-head approval by a current
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
distribution/version, duplicated discovery manifests, and UI entry point. No wheel
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
  `CATALOGUE_POLICY_AUTOMERGE_ENABLED` is exactly `true`. For a clean, mergeable
  certified PR it requests a protected squash merge with the expected head SHA;
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

## Activation checklist — maintain existing protection meanwhile

1. Merge this implementation through the existing `validate` plus one human review
   requirements. Leave the auto-merge variable unset/false. Do not require an
   untested/nonexistent policy check on the implementation PR.
2. Verify installation, exact App permissions and both environment secret names.
   **The observed environment still allows administrator bypass: this is an
   activation blocker.** A maintainer must disable it and confirm branch-only main
   restrictions before relying on the key boundary.
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
