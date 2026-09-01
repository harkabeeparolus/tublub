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

## Dev tooling and testability

- **nox for multi-version test runs.** The pytest `filterwarnings = ["error"]`
  guard was verified on the 3.10 CI leg with a one-off
  `uv run --isolated --python 3.10 pytest`. If local multi-version runs become
  routine, adopt nox (the standard multi-Python runner, with a uv backend)
  rather than accumulating custom uv invocations; pylendar has no existing
  pattern for this either.
- **csv options entangle load and save at the CLI level.** `-d`/`-q`/`--dialect`
  sit in both `load_args` and `save_args` for csv, so a cli-level test of the
  save side must load from JSON to keep the option out of the parse (see
  `test_csv_save_options_reach_the_writer`), and content detection can reroute
  a fixture to tsv so the option under test is never consulted at all. Worth
  exploring a refactor for testability — e.g. collecting `extra_args` into
  per-phase dicts keyed by the input/output formats — without changing the
  flag surface, which deliberately applies one option to both phases.

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

## Test-suite gaps — DONE

Shipped (unreleased): csv's three `save_args` are driven through one real
`-t csv` export from a JSON input (the unix dialect quotes everything, making
each option separately visible; a CSV input would let the same options reshape
the parse) and `-q` through a real load; a new exit-codes section pins parser
rejections at 2 and runtime failures at `sys.exit(message)` (in-process the
code is the message string, which the interpreter maps to status 1); a
two-sheet ODS conversion is asserted through both save and `--list-sheets`,
and HTML/RST book exports keep both sheets with no fallback warning (rst
asserts data, not titles — tablib's rst `export_book` emits none);
`--no-xlsx-optimize` loads a real two-sheet workbook whole, flagged in its
docstring as a tablib-boundary guard because `filter_args`' silent-drop
design leaves no tublub mutation that could fail it; `print_databook`'s
heading-only branch is hit via a selected empty sheet; and
`[tool.pytest.ini_options]` adds `testpaths`, `--strict-markers`, and
`filterwarnings = ["error"]` with no ignores (the suite is warning-clean on
3.10 and 3.14). Declined as over-coverage: a dataset-level ODS test (subsumed
by the book round-trip plus existing binary-path coverage, and the doc claims
are specifically multi-sheet), cli-level and single-sheet `--no-xlsx-optimize`
variants (parse level already covered; no additional failure mode), and a
dedicated exit-0 test (`rc == 0` is asserted throughout). A `--dialect` *load*
test turned out impossible — writing it revealed the flag is inert on load
(now a quirks entry below) — so save-side coverage is all there is.

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
- `--dialect` is silently inert on csv *load* (found 2026-09-01 while closing
  the test gaps): tablib's `import_set` calls
  `kwargs.setdefault("delimiter", ",")` before `csv.reader(in_stream,
  **kwargs)`, and an explicit `delimiter=` keyword overrides the dialect's
  delimiter — so `--dialect excel-tab` still parses commas, and the only
  other read-relevant stdlib dialect difference (`unix`'s QUOTE_ALL) affects
  writing only. Save is unaffected (`unix` quoting demonstrably comes
  through). Fixing means either passing the dialect's delimiter explicitly,
  scoping `dialect` to `save_args` only, or an upstream tablib fix; the
  manual currently says "input/output dialect".
