# TODO — multi-sheet input support

> See also `CODE_REVIEW.md` for orthogonal pre-release polish/refactor
> items (CR-A1 .. CR-F3). Some overlap with this roadmap is noted there
> inline; resolve the cross-referenced architecture items (CR-A1 .. A3)
> before TODO 3+ land where possible.

A staged plan for extending tublub so a single input file with multiple
sheets (XLSX/ODS/XLS/JSON/YAML) can be inspected, displayed, and converted.

The output side is already done: `-o out.xlsx in1 in2 ...` builds a
Databook from multiple inputs. This document covers the input side, where
tublub currently silently loads only the first sheet via
`tablib.import_set()`.

Work the items in order — later ones depend on earlier helpers.

## Don't hard-code a Tablib capability matrix

Mirror the pattern already used in `save_databook_file()`: attempt the
Databook operation and catch `tablib.UnsupportedFormat` (or whatever
tablib raises for parse failure on a nominally-supported format), then
fall back to single-sheet handling. No `databook: bool` field on
`FormatConfig`, no static "which formats support import_book" table —
those would drift from upstream and force us to update tublub every
time tablib gains a new format.

```python
# pattern, mirroring save_databook_file()
try:
    book = tablib.Databook().load(payload, format=fmt, **kwargs)
except (tablib.UnsupportedFormat, KeyError, TypeError):
    book = None  # caller treats as single-sheet
```

`KeyError`/`TypeError` join `UnsupportedFormat` because tablib raises
those when a Databook-capable format (json/yaml) holds a single-Dataset
shape (records list rather than `[{title, data}, ...]`). Both signals
mean the same thing to us: "not a Databook, fall back to Dataset".
Genuine load errors (corrupt files, decode failures) still propagate.

## Behaviour summary

| Invocation | Result |
|---|---|
| `tublub book.xlsx` (multi-sheet, terminal) | Print first sheet + stderr hint about the others |
| `tublub --list-sheets book.xlsx` | List sheets with row × col counts, exit 0 |
| `tublub --sheet Users book.xlsx` | Load only `Users`, behave like a single Dataset |
| `tublub --sheet 0,2 book.xlsx` | Load those two sheets as a Databook subset |
| `tublub --all-sheets book.xlsx` | Print every sheet with heading separators |
| `tublub --all-sheets -o out.xlsx book.xlsx` | Save full Databook (multi-sheet → multi-sheet) |
| `tublub --all-sheets -o out.csv book.xlsx` | Error: target is single-sheet; instruct user to pass `--sheet` |
| `tublub -o out.xlsx book.xlsx users.csv` | Expand `book.xlsx`'s sheets + 1 sheet from `users.csv` into `out.xlsx` |

Single-sheet target formats (csv/tsv/dbf/cli/jira/latex/sql) **never** auto-split
into multiple files. We always require the user to pick a single sheet.

## Critical files

- `src/tublub/main.py` — all CLI / load / save logic.
- `tests/test_main.py` — extend.
- `tests/conftest.py` — add multi-sheet `.xlsx` and `.json` fixtures.
- `CHANGELOG.md`, `README.md` — user-facing docs.

## Reusable existing pieces

- `FormatConfig` / `FORMATS` in `main.py` — keep as-is. Do **not** add a
  `databook: bool` field. Capability is discovered by attempting the
  load and catching `tablib.UnsupportedFormat`, the same way
  `save_databook_file()` already handles the export side.
- `filter_args()` already filters kwargs per format/phase; no change needed.
- `_unique_titles()` — widen signature to accept already-derived titles
  rather than only raw `Path` objects, so step 6 can reuse its `_2`/`_3`
  collision suffix logic.
- `save_databook_file()` already implements the multi-sheet write path;
  reuse unchanged for `--all-sheets -o ...`.
- `TublubError` is the project's user-facing exception — keep the pattern.

---

## TODO 1 — Try-load helper for Databook input

**Goal:** A helper that attempts to load any input as a `tablib.Databook`
and reports success or fallback, without consulting any static capability
table.

**Tasks**
- Add `load_databook_file(path, extra_args, in_format=None) -> tablib.Databook | None`
  paralleling `load_dataset_file()`. It should reuse the same format
  resolution, open-mode, and newline plumbing.
- Inside, call `tablib.Databook().load(fh.read(), format=fmt, **kwargs)`
  and return the book on success.
- Catch `(tablib.UnsupportedFormat, KeyError, TypeError)` and return
  `None`, signalling to the caller "this isn't a Databook; use the
  existing Dataset path". `UnsupportedFormat` covers format-level
  capability (csv/tsv/dbf/...); `KeyError`/`TypeError` cover shape
  mismatches inside json/yaml (records-style content).
- Genuine load errors (corrupt binary files, decode failures, etc.)
  must still propagate — don't swallow real errors.
- Add a thin `load_databook_stdin(...)` counterpart that mirrors the
  existing `load_dataset_stdin()` plumbing.
- The existing `load_dataset_file()` stays as the single-sheet path. New
  callers that want multi-sheet behaviour go through
  `load_databook_file()` first and fall back on `None`.

**Tests** — multi-sheet xlsx returns a Databook with the right size;
csv returns `None`; malformed xlsx still raises (not silently `None`).

---

## TODO 2 — `--list-sheets` flag

**Goal:** A read-only inspection mode that prints sheet metadata.

**Tasks**
- Argparse: add to the input-options group. Mutually exclusive with `-o`,
  `--all-sheets`, `--sheet`, and any output-format flag (similar guarding
  to the existing `--list`).
- Implementation: call `load_databook_file()` from TODO 1. If it returns
  a Databook, iterate its sheets and print
  `f"{title}  {len(ds)} rows × {len(ds.headers or [])} cols"` per sheet.
- If it returns `None` (single-sheet format), fall back to
  `load_dataset_file()` and print one line for the lone synthesised sheet
  using the file stem as title — the flag should work uniformly. Decide
  and document this in `--help`.

**Tests** — multi-sheet xlsx, single-sheet csv, empty workbook, unknown
format, mutual-exclusion errors.

---

## TODO 3 — `--sheet NAME_OR_INDEX` flag

**Goal:** Pick a subset of sheets by name or index. Repeatable.

**Tasks**
- Argparse: `action="append"`, also accept comma-separated values. After
  parsing, flatten + `split(",")` and store as `args.sheets: list[str]`.
- Resolution order for each token: try integer (0-based index), then
  exact title match, then case-insensitive title match. On miss, raise
  `TublubError` listing all available titles.
- Default to **0-based** indices (Python convention); document with an
  example in `--help`. Revisit if pre-PR feedback prefers 1-based.
- Dispatch: 1 sheet selected → existing Dataset code path; >1 selected →
  Databook code path (build a fresh Databook from the chosen subset).
- Mutually exclusive with `--all-sheets` and `--list-sheets`.

**Tests** — pick by name, pick by index, comma list, repeated `--sheet`,
unknown name (error message lists titles), case-insensitive match,
single-sheet input still works (`--sheet 0`).

---

## TODO 4 — `--all-sheets` flag

**Goal:** Opt in to loading every sheet as a Databook.

**Tasks**
- Argparse: `store_true`. Mutually exclusive with `--sheet` and
  `--list-sheets`.
- Dispatch:
  1. No `-o`, no `-t`/`--format`, terminal output → print each sheet with
     a heading separator (see TODO 5).
  2. `-o FILE` → just call `save_databook_file()`. It already catches
     `tablib.UnsupportedFormat` and re-raises as `TublubError(
     "Format X does not support multi-sheet (Databook) output")`. Refine
     that message to mention `--sheet` as the workaround.
  3. `-t FMT` without `-o` (stdout export) → attempt `book.export(fmt)`
     directly and catch `tablib.UnsupportedFormat` the same way; convert
     to a `TublubError` pointing the user at `--sheet`.
- Single-sheet inputs with `--all-sheets` should behave the same as a
  one-sheet Databook (no special-casing).

**Tests** — terminal display, xlsx→xlsx round-trip, xlsx→csv error,
xlsx→json multi-sheet roundtrip, json→yaml roundtrip.

---

## TODO 5 — Heading-separated terminal layout

**Goal:** Implement the printing layout used by `--all-sheets` to a TTY.

**Tasks**
- Add `print_databook(book: tablib.Databook, file_handle=sys.stdout) -> None`.
- For each sheet:
  ```
  === <title> (<N> rows) ===
  <tabulated sheet, current default tablefmt>

  ```
  (One blank line between sheets, none after the last.)
- Honour `--tablefmt` if set, same as today's single-Dataset path.
- Reuse from `export_dataset()` where reasonable; consider extracting a
  `_format_dataset_as_table(ds)` helper used by both single- and multi-
  sheet printing.

**Tests** — capture stdout, assert headings + blank-line separation +
content. Empty sheets should still get a heading.

---

## TODO 6 — Default-mode stderr hint for multi-sheet inputs

**Goal:** Make the existence of extra sheets discoverable without
breaking current behaviour.

**Tasks**
- In single-input mode, attempt `load_databook_file()` (TODO 1) first.
  - On success with `book.size > 1`: take `book.sheets()[0]` as the
    dataset and write one stderr line:
    `f"{file}: {book.size-1} more sheet(s) — use --list-sheets, --sheet, or --all-sheets"`.
  - On success with `book.size == 1`: take that single sheet and emit no
    hint.
  - On `None` (single-sheet format): fall back to `load_dataset_file()`
    as today, no hint.
- Suppress the hint when `--sheet` was given (user already knows there
  are multiples) and when `--list-sheets`/`--all-sheets` are active.
- One file read only — the Databook attempt subsumes the Dataset path on
  Databook-capable formats. Don't re-open the file just to count.
- Decide whether to gate the hint on `sys.stderr.isatty()`. Lean: print
  always (CLI tools normally write to stderr unconditionally); revisit
  if it becomes noisy in scripts.

**Tests** — `tublub sample.xlsx` produces hint; `--sheet 0` does not;
`--all-sheets` does not; single-sheet input does not.

---

## TODO 7 — Multi-input expansion (`_run_databook`)

**Goal:** When one of the inputs in multi-input mode is itself
multi-sheet, expand all of its sheets into the output Databook.

**Tasks**
- In `build_databook()`, try `load_databook_file()` for each input. On
  success, iterate `book.sheets()` and emit titles
  `f"{path.stem}__{sheet.title}"`. On `None` (the helper signalled the
  format isn't Databook-capable), fall back to `load_dataset_file()` and
  keep the current `path.stem` title.
- Generalise `_unique_titles()` to operate on a list of pre-derived
  titles (not just `Path` stems) so the `_2`/`_3` collision suffixes
  still apply uniformly.
- Honour `--sheet` and `--all-sheets` if also given in multi-input mode.
  `--all-sheets` is the implicit default for multi-sheet inputs in this
  mode (point of this TODO). `--sheet X` should be applied uniformly to
  every input that is multi-sheet capable, and ignored on
  non-multi-sheet inputs (or error — decide during implementation).

**Tests** — `tublub -o out.xlsx book.xlsx users.csv` produces a workbook
where book.xlsx's two sheets become two output sheets plus one for
users.csv; sheet-name collision across files gets `_2` suffix.

---

## TODO 8 — Stdin support for multi-sheet inputs

**Goal:** `--list-sheets`, `--sheet`, `--all-sheets` should all work when
input comes from stdin.

**Tasks**
- Use `load_databook_stdin()` (added in TODO 1) before falling back to
  `load_dataset_stdin()`, mirroring the file path. Same try/`None`
  contract.
- Multi-input mode already forbids stdin (`-` with multiple inputs).
  Keep that constraint.

**Tests** — pipe a multi-sheet xlsx into tublub with each flag.

---

## TODO 9 — Tests and fixtures

**Goal:** Cover all the new code paths.

**Tasks**
- Add `multi_sheet_xlsx` and `multi_sheet_json` fixtures in
  `tests/conftest.py` (build them programmatically with tablib).
- Add a `TestMultiSheetInput` class (or split per flag) in
  `tests/test_main.py`.
- Cover per flag: success, empty workbook, missing sheet name,
  out-of-range index, mutual-exclusion of flags, single-sheet-target
  rejection, terminal display formatting, stderr hint
  presence/absence.

---

## TODO 10 — Docs

**Goal:** User-facing documentation.

**Tasks**
- `CHANGELOG.md` under `[Unreleased] / Added`: bullets for
  `--list-sheets`, `--sheet`, `--all-sheets`, multi-input expansion.
- `README.md`: a "Multi-sheet input" section after the existing
  multi-input output example, mirroring its style with worked examples.
- `--help` text for each new flag should include a short example.

---

## Verification when each TODO ships

- `just check` (ruff + mypy/ty + pytest) must pass.
- Manual smoke against a real multi-sheet workbook:
  - `tublub --list-sheets sample.xlsx`
  - `tublub --sheet 0 sample.xlsx`, `tublub --sheet Users sample.xlsx`
  - `tublub --all-sheets sample.xlsx`
  - `tublub --all-sheets -o out.xlsx sample.xlsx` (round-trip)
  - `tublub --all-sheets -o out.csv sample.xlsx` (must error)
  - `tublub -o merged.xlsx sample.xlsx extra.csv` (expansion)
  - Stderr hint: `tublub sample.xlsx 2>err.log; cat err.log`.

## Open questions to resolve during implementation

- 0-based vs 1-based indices for `--sheet`. Lean 0-based (Python
  convention).
- Whether `--list-sheets` on a single-sheet format prints one row
  (uniform) or errors (strict). Lean uniform.
- Title separator for expanded multi-input sheets (`__` vs `:` vs other).
  Lean `__`; `:` was deliberately rejected to keep `book.xlsx::Sheet1`
  syntax available as a future option.
- Whether the stderr hint should respect `NO_COLOR` or a future
  `--quiet` flag. Defer until anyone complains.
