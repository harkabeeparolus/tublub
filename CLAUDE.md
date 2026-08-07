# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is tublub?

A CLI tool that converts between tabular data formats (CSV, JSON, XLSX, YAML, etc.) using the Tablib library.

## Commands

Always run `just lint` after every complete file edit. See `Justfile` for all recipes.

```bash
just lint       # ruff check --fix + ruff format
just typecheck  # mypy + ty
just test       # pytest
just audit      # zizmor audit of .github/ (offline mode)
just check      # all of the above
just run ARGS  # run the CLI from the dev checkout, e.g. `just run --list`
just build_man # pandoc docs/tublub.1.md -> data/ (needs pandoc)
just build     # build_man + uv build; never plain `uv build` for a release
```

## Architecture

Single-module CLI in `src/tublub/main.py`. Entry point: `tublub.main:cli`.
Per-format behavior (binary?, newline, allowed load/save kwargs) lives in the
`FORMATS` dict — adding or tweaking a format means editing that entry, not
sprinkling conditionals through the loaders.

For the design rationale (detection policy, Dataset-vs-Databook split, the
"no static capability matrix" principle, error boundary) read `docs/design.md`
and the decision log in `docs/decisions.md` *before* changing format detection,
error handling, or the load/save split. `docs/TODO.md` holds unscheduled work
that has not been started. `docs/RELEASING.md` is the release procedure.

`docs/tublub.1.md` is the man page source and the authoritative user reference
— a new flag is documented there, not in `README.md`, which is a landing page
(decision 029); `test_man_page_documents_every_long_option` fails if you forget.
`data/` holds the generated roff, is gitignored, and is never edited by hand.

## Changelog & decision log

Always update `CHANGELOG.md` under the `[Unreleased]` section when making user-facing changes (new features, bug fixes, behavior changes). Follow the [Keep a Changelog](https://keepachangelog.com) format with `Added`, `Changed`, `Fixed`, `Removed` subsections.

When a `docs/TODO.md` roadmap item ships, mark its heading `— DONE` and collapse the body to a short "Shipped (unreleased): ..." summary. Once the whole roadmap has shipped and been released, drop the summaries — `CHANGELOG.md` and `docs/decisions.md` already record what landed and why — and keep only the notes that neither of those holds.

Record design decisions as a new numbered entry in `docs/decisions.md`: `### NNN. Title`, `*YYYY-MM-DD · Accepted*`, then **Context** / **Decision** / **Why**. Supersede earlier entries explicitly rather than rewriting them.

A plan or implementation review may find a `docs/TODO.md` task's spec wrong; record the revision as a new decision entry that supersedes the task wording (021 → TODO 5, 024 → TODO 6) and have the `— DONE` summary cite it, rather than quietly rewriting the task.

Not every departure needs a decision entry: a roadmap sub-task that turns out unnecessary or already shipped is just a note in the `— DONE` summary (the multi-sheet roadmap's dropped fixtures task and declined flag table, both still noted in `docs/TODO.md`). Reserve entries for real spec revisions.

## Conventions

- Print statements are allowed (`T20` ignored in Ruff config) since this is a CLI tool.
- Library helpers raise `TublubError` for user-facing problems; only `cli()`
  catches it and converts to `sys.exit(msg)`. Keep new helpers consistent so
  they remain reusable outside the CLI.
- User-facing strings (errors, warnings, hints, `--help`, README) never name
  Tablib internals like `Dataset`/`Databook` — say "sheet(s)"/"multi-sheet"
  (decision 019). Internal names are fine in code, docstrings, and dev docs.
- Docstrings carry rationale in prose, never `(decision NNN)` citations — those
  live only in `docs/` and this file. See `_unique_titles` for the house style.

## GitHub Actions & Dependabot

- Every action in `.github/workflows/` is pinned to a commit SHA with a
  `# vX.Y.Z` comment (zizmor's blanket policy). To add one, resolve the SHA
  with `git ls-remote https://github.com/OWNER/REPO 'refs/tags/vX*'` — for
  annotated tags use the peeled `^{}` commit. Checkout steps set
  `persist-credentials: false`.
- Anything under `.github/` must pass `just audit` — zizmor checks
  `dependabot.yml` too (e.g. requires `cooldown` on update entries).
- Local zizmor runs offline; `zizmor.yml` CI runs the online audits and
  uploads SARIF to code scanning, so CI can find things local runs don't.
- Dependabot bumps action SHAs + version comments and `uv.lock` (grouped,
  monthly, 7-day cooldown) — don't hand-bump pins, merge its PRs instead.
- The one pin Dependabot does *not* maintain is `uv_build` in
  `build-system.requires`, which isn't in `uv.lock`. When uv's minor version
  moves past the range, `uv build` warns that the requirement "does not
  contain the current uv version" — bump it by hand to
  `>=<installed uv>,<next minor>`, the range `uv init` would write.

## Tablib gotchas

- `bool(Databook())` is always `True` — no `__len__`/`__bool__`. Test emptiness
  with `not book.sheets()`; a `if not data:` guard is dead code for Databooks.
- `Databook.export(fmt)` raises `UnsupportedFormat` for csv/tsv/dbf/cli/jira/
  latex/sql at *any* size, size 1 included — capability is per-format, not
  per-book. Book-capable: html/json/ods/rst/xls/xlsx/yaml. Size *0* is the
  exception: an empty book raises `IndexError` from xls/xlsx (openpyxl needs
  one visible sheet), so capability can't be probed with a throwaway
  `Databook()` — attempt the real export (decision 026).
- `import_set()` on a book-shaped JSON/YAML (`[{title, data}, ...]`) silently
  yields a bogus two-column `title`/`data` Dataset — which is why the
  `try_load_*` handshake tries Databook first.

## Ruff gotchas

- RUF001/2/3 flag ambiguous Unicode (e.g. `×`, `−`, `–` EN DASH) in strings, comments, and docstrings — use ASCII equivalents. Em dash `—` is *not* flagged and is used freely in `src/`.
- SIM108 turns `if/else` value-assignment into a ternary; if the ternary would nest ugly, build a base value then mutate it (e.g. `mode = "w" if write else "r"; if binary: mode += "b"`) instead of fighting it.
- C901/PLR0912 cap functions at ~10 cyclomatic / ~12 branches — extract a helper before piling more guards into `_validate_args` or `cli`.
- S101 forbids `assert` in `src/` (tests get it via per-file-ignores). For type narrowing, use an explicit `if x is None: raise TublubError(...)` instead, or extract a helper whose return type is already narrow (see `_default_export_handle`) rather than reaching for `typing.cast`.
- D301 rejects backslashes in docstrings — spell out characters (e.g. "backslash") or prefix the docstring with `r"""`.
- ANN401 forbids `Any` in signatures, and annotating Tablib's untyped `export()`
  payload as `str | bytes` then trips mypy when writing it to `IO[str] | IO[bytes]`.
  Don't return the payload — mirror `export_dataset`/`export_databook`: take an
  optional `file_handle`, keep the payload in a local, and write it there.

## Testing patterns

- Verifying CLI error paths: `just run` swallows stderr and only reports the exit code on failure. Run `uv run tublub ARGS` directly to see the actual `parser.error`/`sys.exit` message.
- Proving a test can fail: for *new* behaviour write the test first and watch it
  fail against the unchanged source — same signal as mutating, minus the risk.
  With the implementation already written but uncommitted, get that red run back
  with `git stash push src/tublub/main.py` (pathspec form — a bare `git stash`
  would take the new tests too) then `git stash pop`: un-applying your own diff
  is the most faithful mutation and `pop` restores it byte-exactly. Only for
  *committed* code does hand-mutating apply, and the same stash brackets it:
  `git stash push src/tublub/main.py` to park your work, mutate, watch it go red,
  then `git restore src/tublub/main.py` to drop only the mutation and
  `git stash pop` to bring your work back. Don't revert the mutation with Edit —
  restore is exact and cannot leave a stray edit behind. `git checkout` /
  `git restore <file>` on a file holding *unstashed* work discards it — and stash
  cannot get it back afterwards, it only prevents the loss.
- Argparse unit tests: call `parse_command_line(argv)` directly and assert on the returned `args`.
- CLI integration tests: call `cli([...])` with an argv list, read `capsys.readouterr().out`.
- Don't monkeypatch `sys` globals — the IO edges take injection params (decision 020):
  `parse_command_line(argv, stdin_isatty=True/False)` for input-presence/implicit-stdin
  paths, `stdin=io.BytesIO(...)` for the stdin loaders, `stdout=` for
  `_default_export_handle`, `cli(prompt_input=io.StringIO("y\n"))` for the
  overwrite answer. Gate on the injected *bool*, never `stream.isatty()` — an
  injected `StringIO`/`BytesIO` always reports False, which would make the TTY
  path untestable.
- Decision 020's ban covers `sys` globals only — `monkeypatch.setattr("tublub.main.get_formats", ...)`
  is fine (used to simulate a Tablib install without the `cli` format).
- Byte-exact output checks: `diff <(uv run tublub a.csv) <(uv run tublub -t cli a.csv)`
  for render identity; `uv run tublub -t json a.csv | xxd | tail -1` for trailing newlines.
- Rejection tests use `pytest.raises(SystemExit)` since `parser.error()` exits.
  For a combo involving a *new* flag, also assert the message
  (`"Can not combine" in capsys.readouterr().err`) — unrecognized arguments
  exit 2 too, so a bare `SystemExit` test is already green before you implement.
- Tests are module-level `def test_` functions grouped under `# --- section ---`
  comments (bare `# text` comments mark sub-groups within a section); no
  `Test*` classes, no `unittest.TestCase`.
- Smoke-testing TTY-gated output needs a real terminal:
  `script -qec "uv run tublub FILE >/dev/null" /dev/null`. The Bash tool runs
  `/bin/bash`, not the user's fish — use `<(...)`, not `psub`. For TTY-gated
  *input* (the overwrite prompt), feed the answer through `script`'s own stdin:
  `script -qec "uv run tublub a.csv existing.json" /dev/null <<< "y"`. Piping
  into `script` instead (`echo y | script -qec ...`) replaces the pty on stdin,
  so `isatty()` is False and the gate never opens.
- Test CSV fixtures need 2+ columns: `detect_format` returns `None` on a
  single-column CSV, so it falls through to the TSV heuristic and every load
  prints "Extension suggests csv but content detected as tsv".
- `tmp_path.name` is ~31 chars — the same as `XLSX_TITLE_LIMIT` — so titles
  qualified by it clamp to just the directory name. Assert exact qualified
  titles against a short `tmp_path` subdirectory instead.
- No multi-sheet workbook is tracked in the repo; build smoke-test inputs in
  the scratchpad with tablib (`Databook()` + `export("xlsx")`). Untracked
  sample files in the repo root are ad hoc — don't assume they exist.
