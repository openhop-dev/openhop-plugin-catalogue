# Adding a third-party app to the openHop catalogue

The openHop plugin catalogue is a curated directory of reviewed plugin releases. Third-party developers are welcome to submit apps, but publishing a wheel or passing automated checks does not by itself make an app an approved openHop plugin.

**A pull request (PR) is required to add an app to the catalogue. The openHop team must review the app before approving it for inclusion.**

## Test your app first — no catalogue PR required

Start with [Build a Repeater plugin wheel](plugin-wheel-development.md) for the
source-grounded manifest/runtime contract, a minimal Python packaging example,
and a parser check that needs no running Repeater or hardware.

You do not need a catalogue listing, an approval, or a PR to develop and test your app:

1. Package your app as an openHop-compatible Python wheel (`.whl`), including its plugin manifest and required runtime/UI files.
2. Upload the wheel directly to your own openHop Repeater installation using its plugin upload/install functionality.
3. Test installation, configuration, startup, normal operation, and removal. Test upgrades as appropriate, and document the Repeater version you used.

Uploading a wheel to your own installation is separate from submitting it to this catalogue. It does not publish the app to other users or grant approved-plugin status. Only install wheels you trust; use a test installation and avoid exposing production credentials or data while developing.

## Prepare a submission

Before requesting a listing:

- Make the app and its source available for openHop team review. Identify the exact source commit used for the proposed release. If source and release repositories differ, explain that relationship in the PR.
- Document what the app does, how to configure and use it, its dependencies, compatible Repeater versions, and any external services or accounts it requires.
- Explain the permissions, network access, credentials, and user data the app uses. Describe any radio transmissions or other operational side effects.
- Include license information for the app and bundled components, a maintenance/contact route, and installation/testing results.
- Publish a versioned `.whl` asset on the app's public GitHub Release. Keep the wheel's distribution, version, and plugin identity consistent with its metadata and manifest.
- Download the published wheel again and calculate its SHA-256. Submit the checksum of those public bytes, not a different local build.

Do not replace the bytes of an approved release asset or delete releases still referenced by the catalogue. Publish a new version for changes.

## Open a catalogue PR

1. Fork [openhop-dev/openhop-plugin-catalogue](https://github.com/openhop-dev/openhop-plugin-catalogue) and create a branch from current `main`.
2. Add your entry to [`catalogue.json`](../catalogue.json), following the [schema-2 field reference](../README.md#catalogue-entry-format-schema-2). Include the app's identity and display metadata, artifact repository, distribution, version, exact source revision, versioned wheel URL, and published-wheel SHA-256. Include compatibility information where applicable.
3. Keep the change focused on your app. **Do not commit the wheel, plugin source, credentials, or private keys to the catalogue repository.** This repository stores metadata only; release assets stay in your app's repository.
4. Run the [local validation commands](../README.md#local-validation) from the catalogue checkout.
5. Open a PR against `main`. A draft PR is appropriate while preparing the submission; mark it ready when you want the completed app considered for approval.

Include in the PR description:

- What the app does and who maintains it.
- Source repository and exact build-source commit.
- Public release and direct wheel download links.
- Proposed version and published-wheel SHA-256.
- Supported/tested Repeater versions and installation/configuration instructions.
- Testing results and known limitations.
- License, dependencies, external services, and permission/data-use details.

## Team review and approval

The openHop team reviews the app, not just the catalogue JSON. Supply enough source, documentation, and test evidence for the team to assess its behavior, compatibility, packaging, dependencies, and security implications. Reviewers may request changes or additional testing before approval.

Automated validation is required, but a green check is not a substitute for team review. Submitting a PR does not guarantee acceptance. Initial catalogue additions follow the human-reviewed approval path.

After approval and merge, the catalogue's publishing service distributes the updated metadata. Users can then discover the approved release through the catalogue and download its wheel from your GitHub Release. Your existing local test installation does not need a catalogue listing to keep working.

## Updating an approved app

Catalogue updates also go through PRs. By default, publish the new release, verify its public wheel, and submit a focused PR updating your app's release metadata for review.

Catalogue inclusion and automatic publishing are separate decisions. An approved listing does **not** automatically grant a third-party repository permission to publish unattended updates.

The openHop team may separately authorize automatic release updates by configuring a trusted publisher and a catalogue-owned registration. In that arrangement, release automation creates the PR, and the catalogue verifies the registered app, release, checksum, and permitted changes before automatically merging it. The producer cannot approve itself, change its own publishing policy, or bypass required checks. Branding, compatibility, policy changes, and initial registrations remain subject to the appropriate human-reviewed path.

Do not copy another app's publisher credentials or add yourself to the automatic-publishing registry as a shortcut to approval. Coordinate any automation setup with the openHop team. See the [publishing policy](publishing-policy.md) for the technical boundaries.
