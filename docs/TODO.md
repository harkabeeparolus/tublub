# TODO — multi-sheet input support

> See [`design.md`](design.md) for the architecture and principles this
> roadmap builds on, and [`decisions.md`](decisions.md) for the pre-release
> review decisions (the former CODE_REVIEW.md findings, now resolved).

A staged plan for extending tublub so a single input file with multiple
sheets (XLSX/ODS/XLS/JSON/YAML) can be inspected, displayed, and converted.

The output side is already done: `-o out.xlsx in1 in2 ...` builds a
Databook from multiple inputs. This document covers the input side, where
tublub currently silently loads only the first sheet via
`tablib.import_set()`.

Work the items in order — later ones depend on earlier helpers.

## Don't hard-code a Tablib capability matrix

The guiding principle and its rationale now live in
[`design.md` § No static Tablib capability matrix](design.md#no-static-tablib-capability-matrix)
and [`decisions.md` 002](decisions.md). In short: discover capability by
attempting the Databook operation and catching failure, never by a static
table. The actionable pattern for the items below:

```python
# pattern, mirroring save_databook_file()
try:
    book = tablib.Databook().load(payload, format=fmt, **kwargs)
except (tablib.UnsupportedFormat, KeyError, TypeError):
    book = None  # caller treats as single-sheet
```

## Behaviour summary

| Invocation | Result |
|---|---|
| `tublub book.xlsx` (multi-sheet, terminal) | Print first sheet + stderr hint about the others |
| `tublub --list-sheets book.xlsx` | List sheets with row × col counts, exit 0 |
| `tublub --sheet Users book.xlsx` | Load only `Users`, behave like a single Dataset |
| `tublub --sheet 0,2 -o out.xlsx book.xlsx` | Save those two sheets as a Databook subset (multi-sheet selection requires `-o`; bare-terminal multi-display is `--all-sheets`' job) |
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
- For a single-sheet result, report only what was observed (decision 016):
  print one line with the real title when the loaded object carries one
  (a size-1 Databook, e.g. a one-sheet XLSX), no title for a fallback
  Dataset (CSV / records-shaped JSON), and **no `[index]`** in either
  case. Do not synthesise a `[0] {stem}` line — that would imply a sheet
  index and invite `--sheet 0`, which TODO 3 rejects on single-sheet
  inputs. `sheet.title` truthiness distinguishes the two origins without
  re-checking the loaded type or a format table. Document in `--help`.

> **Note (decision 016):** the originally-shipped 0.5.0 behaviour printed a
> fabricated `[0] {stem}` line for single-sheet inputs. That is superseded by
> the observational form above; the change ships alongside TODO 3.

**Tests** — multi-sheet xlsx, single-sheet csv, empty workbook, unknown
format, mutual-exclusion errors.

---

## TODO 3 — `--sheet NAME_OR_INDEX` flag

**Goal:** Pick a subset of sheets of a multi-sheet input by name or index.
Repeatable.

Design decisions for this item are recorded in
[`decisions.md` 016](decisions.md). The summary below reflects them; where
this section once differed (notably "single-sheet input still works
`--sheet 0`"), 016 supersedes it.

**Parsing & validation**
- Argparse: `action="append"`, dest `sheet`, default `None`. In
  `parse_command_line` flatten on commas, strip each token, drop empties,
  and store as `args.sheets: list[str]`. An empty result (e.g.
  `--sheet ,`) is a usage error ("no sheet selector given").
- Add `_validate_sheet` mirroring `_validate_list_sheets`: reject combining
  with `--list`, `--list-sheets` (and `--all-sheets` once it exists),
  reject stdin and 2+ inputs, and require an input file. **Single local
  file only** in this increment — stdin is TODO 8, multi-input is TODO 7.

**Resolution (per token)**
- An integer-looking token is **always** a 0-based index. Out of range →
  `TublubError` "index N out of range (0-M)"; never fall back to a title
  match. 0-based is consistent with what `--list-sheets` prints.
- A non-integer token matches a title: exact first, then case-insensitive.
  On miss, `TublubError` listing all available titles.
- Resolve against a shared `_sheets_of(loaded) -> list[tablib.Dataset]`
  normaliser (a Databook's `.sheets()`, or `[dataset]` for the fallback
  Dataset) so `--list-sheets` and `--sheet` can't drift.

**Dispatch (`_run_sheets`, dispatched from `cli()` before the 2+ inputs
branch)**
- **Single-sheet input** (the normalised list has length 1): reject with
  the observational message "input resolved to a single sheet; `--sheet`
  applies to multi-sheet inputs" — *not* a capability claim (008/016). This
  covers a 1-sheet XLSX (size-1 Databook) and a CSV/records-JSON (fallback
  Dataset) alike; rejection is about the observed sheet count, not the
  format.
- **1 sheet selected** from a multi-sheet input → extract that Dataset and
  render it through the existing single-Dataset path. Extract
  `_render_dataset(ds, args, extra_args)` from the tail of `_run_single`
  (save to `-o` / export via `-t` / print) so this path reuses the real
  renderer and can't drift.
- **>1 sheet selected** → build a fresh Databook from the chosen subset, in
  **selection order**, deduping by resolved sheet identity (two tokens
  hitting the same sheet keep the first, drop the rest silently). Output:
  reuse `save_databook_file` (requires `-o`). With no `-o`, error
  "selecting multiple sheets requires `-o FILE`; terminal display comes
  with `--all-sheets`" — multi-sheet terminal print is TODO 5 and
  Databook-to-stdout `-t` export is TODO 4, both deferred.

**Tests** — pick by name, pick by index, comma list, repeated `--sheet`,
selection-order preserved, duplicate tokens deduped, unknown name (error
lists titles), case-insensitive match, out-of-range index errors,
single-sheet input rejected (`--sheet 0 users.csv` and a 1-sheet xlsx both
error), multi-select without `-o` errors, multi-select to a single-sheet
target (`-o out.csv`) errors via `save_databook_file`, mutual-exclusion and
stdin/multi-input rejection.

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

- ~~0-based vs 1-based indices for `--sheet`.~~ **Resolved: 0-based**
  (decision 016), consistent with `--list-sheets` output.
- ~~Whether `--list-sheets` on a single-sheet format prints one row or
  errors.~~ **Resolved: prints one observational row** (real title if
  present, no synthesised `[index]`/stem-title); `--sheet` on a
  single-sheet input is *rejected* (decision 016).
- Title separator for expanded multi-input sheets (`__` vs `:` vs other).
  Lean `__`; `:` was deliberately rejected to keep `book.xlsx::Sheet1`
  syntax available as a future option.
- Whether the stderr hint should respect `NO_COLOR` or a future
  `--quiet` flag. Defer until anyone complains.
