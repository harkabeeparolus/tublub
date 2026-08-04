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
```

## Architecture

Single-module CLI in `src/tublub/main.py`. Entry point: `tublub.main:cli`.
Per-format behavior (binary?, newline, allowed load/save kwargs) lives in the
`FORMATS` dict — adding or tweaking a format means editing that entry, not
sprinkling conditionals through the loaders.

For the design rationale (detection policy, Dataset-vs-Databook split, the
"no static capability matrix" principle, error boundary) read `docs/design.md`
and the decision log in `docs/decisions.md` *before* changing format detection,
error handling, or the load/save split. `docs/TODO.md` is the multi-sheet
feature roadmap.

## Changelog & decision log

Always update `CHANGELOG.md` under the `[Unreleased]` section when making user-facing changes (new features, bug fixes, behavior changes). Follow the [Keep a Changelog](https://keepachangelog.com) format with `Added`, `Changed`, `Fixed`, `Removed` subsections.

When a `docs/TODO.md` roadmap item ships, mark its heading `— DONE` and collapse the body to a short "Shipped (unreleased): ..." summary (see TODO 1 for the pattern).

Record design decisions as a new numbered entry in `docs/decisions.md`: `### NNN. Title`, `*YYYY-MM-DD · Accepted*`, then **Context** / **Decision** / **Why**. Supersede earlier entries explicitly rather than rewriting them.

A plan or implementation review may find a `docs/TODO.md` task's spec wrong; record the revision as a new decision entry that supersedes the task wording (021 → TODO 5, 024 → TODO 6) and have the `— DONE` summary cite it, rather than quietly rewriting the task.

Not every departure needs a decision entry: a roadmap sub-task that turns out unnecessary or already shipped is just a note in the `— DONE` summary (TODO 8's fixtures, TODO 9's declined flag table). Reserve entries for real spec revisions.

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

## Tablib gotchas

- `bool(Databook())` is always `True` — no `__len__`/`__bool__`. Test emptiness
  with `not book.sheets()`; a `if not data:` guard is dead code for Databooks.
- `Databook.export(fmt)` raises `UnsupportedFormat` for csv/tsv/dbf/cli/jira/
  latex/sql at *any* size, size 1 included — capability is per-format, not
  per-book. Book-capable: html/json/ods/rst/xls/xlsx/yaml.
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
  fail against the unchanged source — that is the same signal as mutating, minus
  the risk. Mutation is only for reworked tests over code that already works;
  apply *and revert* it with Edit, never `git checkout <file>`, which also
  discards the uncommitted implementation you are testing.
- Argparse unit tests: call `parse_command_line(argv)` directly and assert on the returned `args`.
- CLI integration tests: call `cli([...])` with an argv list, read `capsys.readouterr().out`.
- Don't monkeypatch `sys` globals — the IO edges take injection params (decision 020):
  `parse_command_line(argv, stdin_isatty=True/False)` for input-presence/implicit-stdin
  paths, `stdin=io.BytesIO(...)` for the stdin loaders, `stdout=` for
  `_default_export_handle`.
- Decision 020's ban covers `sys` globals only — `monkeypatch.setattr("tublub.main.get_formats", ...)`
  is fine (used to simulate a Tablib install without the `cli` format).
- Byte-exact output checks: `diff <(uv run tublub a.csv) <(uv run tublub -t cli a.csv)`
  for render identity; `uv run tublub -t json a.csv | xxd | tail -1` for trailing newlines.
- Rejection tests use `pytest.raises(SystemExit)` since `parser.error()` exits.
- Tests are module-level `def test_` functions grouped under `# --- section ---`
  comments (bare `# text` comments mark sub-groups within a section); no
  `Test*` classes, no `unittest.TestCase`.
- Smoke-testing TTY-gated output needs a real terminal:
  `script -qec "uv run tublub FILE >/dev/null" /dev/null`. The Bash tool runs
  `/bin/bash`, not the user's fish — use `<(...)`, not `psub`.
- Test CSV fixtures need 2+ columns: `detect_format` returns `None` on a
  single-column CSV, so it falls through to the TSV heuristic and every load
  prints "Extension suggests csv but content detected as tsv".
- `tmp_path.name` is ~31 chars — the same as `XLSX_TITLE_LIMIT` — so titles
  qualified by it clamp to just the directory name. Assert exact qualified
  titles against a short `tmp_path` subdirectory instead.
- No multi-sheet workbook is tracked in the repo; build smoke-test inputs in
  the scratchpad with tablib (`Databook()` + `export("xlsx")`). Untracked
  sample files in the repo root are ad hoc — don't assume they exist.
