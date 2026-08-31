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

The three sections below came out of the 2026-08-31 code audit (the fixes
that landed immediately did so with decision 033). Each open item needs its
own analysis before acting — some may turn out to be deliberate or not worth
the churn.

## Release and CI plumbing — DONE

Shipped (unreleased): `python-publish.yml` checks the release tag against
the `pyproject.toml` version, runs `just ci`, and builds with `just build`
instead of re-implementing it; `tests.yml` gained `timeout-minutes` and a
cancel-in-progress concurrency group; mypy config moved to `[tool.mypy]`
(covering `tests/`, with a per-module ignore for tablib only); Beta and
Python 3 classifiers added; `zizmor.yml` triggers normalized to match
`tests.yml`. Two findings resolved as deliberate, no decision entry (CI
tightening is not architecture): the matrix keeps running full `just ci`
because typecheck results vary by interpreter and the duplicated ruff run
costs about a second, and per-version Python classifiers were declined
because `requires-python` already advertises the floor and a version list
rots.

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
