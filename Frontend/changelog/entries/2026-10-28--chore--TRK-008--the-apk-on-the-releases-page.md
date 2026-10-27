---
date: 2026-10-28
type: chore
title: The APK on the Releases page
dataIds:
  - TRK-008
author: Nakul Srivastava
breaking: false
---

## Before

The signed APK was attached to its workflow run as a zipped artifact. To get it, you had to find the run, unzip the download, and fetch it again within 90 days.

## Now

- Every signed build is also published on the repo's **Releases** page:
  - one release per version, tagged `android-v<version>` and titled "Polysil app <version>";
  - the APK is named for the site it opens, for example `polysil-tracking-0.1.1-crm.polysilirrigation.com.apk`.
- **Another site:** a build for the test site adds its own APK to the same release, so it never replaces the client's.
- **Same version again:** that APK is replaced.
- The run's artifact stays as before.

## Discussion

- **Write permission:** only the signed-release job may write to the repo's contents, which it needs to publish a release. Pull request builds stay read only.
- **Private repo:** a release can only be downloaded by someone with access to the repo, as with the artifacts. Staff without GitHub still get the APK by WhatsApp or Drive.

## Files changed

- `.github/workflows/android-apk.yml`: the release job's `contents: write` permission, the version as a step output, and the "Publish it as a release" step.
- `mobile/README.md`: where to find releases.

## Tests

- The workflow file parses as YAML.
- The first run on `staging` publishes `android-v0.1.1`. Its result is noted in the pull request.
