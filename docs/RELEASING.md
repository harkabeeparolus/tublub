# Releasing tublub

The whole release is one commit titled `Version X.Y.Z` plus a tag and a
draft GitHub release. Established at 0.5.0/0.6.0; see those commits for
worked examples.

1. **Stamp the changelog.** Insert `## [X.Y.Z] - YYYY-MM-DD` directly below
   the empty `## [Unreleased]` heading. The existing entries stay put and
   fall under the new heading; `[Unreleased]` is left empty on top.
2. **Bump the version:** `uv version --bump minor` (or `patch`). This
   updates `pyproject.toml` and re-locks `uv.lock`; nothing else hardcodes
   the version (`__version__` comes from package metadata).
3. **Verify:** `just check` passes and `uv run tublub --version` prints the
   new version.
4. **Commit, tag, push.** Subject exactly `Version X.Y.Z`. Annotated tag
   `vX.Y.Z` (the `v` prefix is decision 014) with the same `Version X.Y.Z`
   message. Push main and the tag.
5. **Draft release:** `gh release create vX.Y.Z --draft --title vX.Y.Z
   --notes-file ...`. Notes are a short elevator pitch, not the changelog
   pasted in: runnable example commands, a breaking-changes warning if any,
   an emoji or two, and a link to `CHANGELOG.md` at the tag
   (`https://github.com/harkabeeparolus/tublub/blob/vX.Y.Z/CHANGELOG.md`).
6. **Stop at the draft.** The maintainer reviews and publishes manually.
   Publishing is the trigger: `.github/workflows/python-publish.yml` runs on
   `release: published` and uploads to PyPI via trusted publishing. A draft
   fires nothing. The workflow fails before building unless the release tag
   equals `v` plus the `pyproject.toml` version, so a mis-tagged release
   publishes nothing; it also runs the full `just ci` first.

Nothing here builds the man page by hand: the publish workflow runs
`just build`, which stamps the page with the version from `pyproject.toml`,
so step 2 is what sets it. To build a distribution locally, use `just build`
(needs pandoc) rather than a bare `uv build`, which would ship a wheel with
no man page.

## Troubleshooting

**Publishing the release fired no workflow run.** GitHub drops events during
Actions outages, and dropped events are never replayed. Nothing in the repo is
wrong and no new version is needed: wait for the outage to clear, then retry.

To tell an outage from a real problem, check whether recent *pushes* also missed
their zizmor run (`gh run list`) and confirm on githubstatus.com. To retry once
it is resolved, `gh release edit vX.Y.Z --draft` then
`gh release edit vX.Y.Z --draft=false` re-fires `release: published` without
touching the tag. Deleting and recreating the release works too — but neither
does anything while the outage is still on, so retrying early looks like a
second failure. First hit at 0.7.0.
