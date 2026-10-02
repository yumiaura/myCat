# WinGet publishing

The first [myCat submission](https://github.com/microsoft/winget-pkgs/pull/445631)
must be merged before automatic updates can use it as a base.
The YAML files in this folder are the initial submission reference; do not edit
them for each release.

## One-time setup

1. Keep the `yumiaura/winget-pkgs` fork under the release repository owner's account.
2. Create a classic GitHub personal access token with `public_repo` and `workflow`
   scopes, as required by [WinGet Releaser](https://github.com/vedantmgoyal9/winget-releaser).
   The `workflow` scope lets it synchronize the fork with upstream workflow changes.
3. Add it as the `WINGET_TOKEN` repository Actions secret in
   [myCat settings](https://github.com/yumiaura/myCat/settings/secrets/actions).
   Do not put the token in a file, issue, or chat. Renew the secret before its token expires.

## Each release

`release-binaries.yml` calls `publish-winget.yml` after its `release` job succeeds,
so the executable is already attached. Stable tags such as `0.1.38` and `v0.1.38`
are supported; drafts, prereleases, and other tag formats are skipped.
Manual build-only runs of Release binaries do not submit WinGet updates.

WinGet Releaser selects only `mycat-windows-x64.exe`, updates the version, URL and
SHA256, and opens a PR in `microsoft/winget-pkgs`. Its action revision is pinned
in the workflow. Existing package metadata comes from the accepted manifest.
Older versions are retained. Publication still depends on WinGet validation and
acceptance of the PR.

Missing credentials or an unmerged first package make the WinGet job fail visibly;
the already uploaded release assets remain available.

## Retry

After fixing an error, use **Re-run failed jobs** on Release binaries. Alternatively,
when the workflow is on the default branch, open **Actions > Publish to WinGet >
Run workflow** and enter the existing release tag. This does not rebuild binaries.
Check for an existing PR for that version before manually retrying a submission.
