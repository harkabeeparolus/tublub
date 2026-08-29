# TODO — unscheduled work

Ideas that are not scheduled and not commitments. See [`design.md`](design.md)
for the architecture they build on and [`decisions.md`](decisions.md) for the
decision log. Each item below needs its own decision entry when it lands.

Multi-sheet input support shipped 2026-08-05 — see `CHANGELOG.md` `[0.6.0]`
for what landed and [`decisions.md`](decisions.md) 016-024 for why. Two
sub-tasks from that roadmap were dropped rather than shipped, noted here
because nothing else records them:

- **Dedicated test fixtures.** They landed incrementally alongside each
  feature, so `tests/conftest.py` already carried every fixture the roadmap's
  fixtures task listed by the time that task came up.
- **A flag table in `README.md`.** Declined — README has never had one and
  `--help` is the single source of truth for the flag surface, so adding one
  would have introduced a second list to keep in sync.

---

## Smaller multi-sheet extensions

- `book.xlsx::Sheet1` per-input selection — the `::` separator stays
  reserved for this (and is why `__` was chosen for expansion titles).
  Unlocks selection in multi-input mode.
- `--exclude-sheet NAME` — "everything but the Notes sheet".
- `--list-sheets -t json` machine-readable listing — would lift the
  `--list-sheets`/`-t` mutual exclusion; don't foreclose it, don't build it
  yet.
- `--skip-lines` on a *single-sheet* workbook still loses the sheet
  structure to the option fallback (decision 032 stops the multi-sheet data
  loss only): `-l` prints the bare `rows x cols` line and `-s 0` says the
  input has no sheet structure. No data loss — the one sheet is read and the
  option applied — but the listing shape lies about the input.

---

The three sections below are the unfixed findings from the 2026-08-31 code
audit (the fixed ones landed with decision 033). Each needs its own analysis
before acting — some may turn out to be deliberate or not worth the churn.

## Release and CI plumbing

- `python-publish.yml` re-implements `just build` (build_man, then
  `uv build`) instead of invoking the recipe, so the release path can drift
  from the Justfile — `RELEASING.md` already warns that a bare `uv build`
  ships a wheel with no man page.
- Nothing checks the release tag against the `pyproject.toml` version at
  publish time; a mis-tagged release publishes the wrong version.
  `RELEASING.md` leaves that invariant manual.
- `tests.yml` runs the full `just ci` (lint + typecheck + test) on every
  matrix Python, but lint/format/typecheck results do not vary by
  interpreter. Also no `timeout-minutes` and no cancel-in-progress
  concurrency group.
- The Justfile runs mypy on `src` only (ty checks the whole tree, so
  `tests/` is never mypy-checked), and `--ignore-missing-imports` is a
  command-line flag rather than `[tool.mypy]` config, so a bare `mypy` or
  editor run uses different settings than CI.
- `pyproject.toml` has no `Programming Language :: Python` or
  `Development Status` classifiers, so PyPI advertises no supported
  versions despite the CI matrix.
- `zizmor.yml` triggers on `pull_request: branches: ["**"]` while
  `tests.yml` uses a bare `pull_request:` — harmless today, easy to
  diverge.

## Test-suite gaps

- `-q/--quotechar` and `--dialect` have parse-level tests only; nothing
  drives them through a real load or save. `-d/--delimiter` is tested on
  load but not on save, though all three sit in csv's `save_args`.
- No test asserts an exit code (`excinfo.value.code`), although the manual
  documents 1 vs 2 as part of the interface.
- ODS appears in no test at all, though README and the manual promise
  multi-sheet ODS output; the HTML/RST book-export claims are likewise
  untested (both formats do have `export_book` in tablib).
- `--no-xlsx-optimize` is parse-level only — never driven through a real
  XLSX load.
- No `[tool.pytest.ini_options]`: no `testpaths`, no `--strict-markers`,
  and no `filterwarnings = ["error"]`, so a regression of the openpyxl
  "Title is more than 31 characters" warning (fixed in 0.5.0) would pass
  silently.
- `print_databook`'s heading-only branch (a selected sheet whose body
  renders empty) is never hit by any test.

## Small behavior and docs quirks

- `_is_int_token` accepts every `int()` spelling — `1_0` selects index 10,
  `+1` index 1, padded whitespace parses — looser than 030's bare-decimal
  rule for range endpoints. Any tightening must keep `-s -1` erroring as
  index -1 (the guarantee 030 leans on), and `name:` already rescues titles
  shaped like these.
- `-H/--no-headers` is silently dropped for xlsx/xls/ods input even though
  tablib's `import_set` accepts `headers=` there. The manual scopes the
  flag to CSV/TSV, so this is a capability question (widen `load_args`?)
  rather than a doc bug — but the silent drop is invisible to users.
- The manual's SHEET SELECTION text says indexed lines are selectable "by
  index or by title"; empty-titled sheets (reachable by index only) and
  duplicate titles (an ambiguity error) are undocumented exceptions.
- `CHANGELOG.md` declares Keep a Changelog but defines no link references,
  so every `[X.Y.Z]` heading renders as literal brackets.
