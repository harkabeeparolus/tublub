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
   fires nothing.
