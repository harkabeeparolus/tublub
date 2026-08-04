# TODO — multi-sheet input support

> See [`design.md`](design.md) for the architecture and principles this
> roadmap builds on, and [`decisions.md`](decisions.md) for the decision log.
> Decisions **016–018** define the CLI surface below; 017 supersedes 016's
> single-sheet rejection rule and list format. Respec'd 2026-07-04 after a
> design review; item numbers changed (old TODOs 3/4/5 merged into today's
> TODO 4 — decision 016's "TODO 3" refers to the old numbering).
> Decision **021** (2026-08-04, TODO 4 plan review) respec'd TODO 5: default
> conversion goes whole-book when the target can hold it.

A staged plan for extending tublub so a single input file with multiple
sheets (XLSX/ODS/XLS/JSON/YAML) can be inspected, displayed, and converted.

Already shipped: multi-input Databook *output* (`-o out.xlsx in1 in2 ...`),
the `try_load_*` helpers (old TODO 1), and a first `--list-sheets` (0.5.0,
output shape revised by TODO 3 below). This document covers the rest of the
input side, where tublub still silently loads only the first sheet.

Work the items in order — later ones depend on earlier helpers.

## The surface in three rules

1. **`--sheet` picks sheets; selection never changes where output may go.**
   One selected sheet behaves exactly like a single-sheet input does today;
   several behave like a multi-sheet workbook — printed with headings, saved
   with `-o`, exported with `-t` — wherever the output format can hold
   multiple sheets. `--all-sheets` is sugar for "select everything".
2. **You can select exactly what `--list-sheets` shows.** Indexed lines
   (`[0] Users ...`) are selectable by index or title; a bare line means the
   input has no sheet structure and nothing to select.
3. **Commas are for index lists; repeat `--sheet` for names; `name:` forces
   a title.**

## Don't hard-code a Tablib capability matrix

The guiding principle and its rationale live in
[`design.md` § No static Tablib capability matrix](design.md#no-static-tablib-capability-matrix)
and [`decisions.md` 002/008](decisions.md). Discover capability by attempting
the Databook operation and catching failure, never by a static table. The
shipped `load_databook_file()` / `try_load_file()` implement this on the load
side; `save_databook_file()` / `book.export()` attempts implement it on the
save side.

## Behaviour summary

| Invocation | Result |
|---|---|
| `tublub book.xlsx` (terminal) | Print first sheet; stderr advice about the rest, gated on TTY |
| `tublub book.xlsx out.ods` | Convert **all** sheets — default conversion goes whole-book when the target can hold it (021) |
| `tublub book.xlsx out.csv` | Fallback: convert first sheet; **always** warn "converting only the first of N sheets" |
| `tublub -l book.xlsx` | `[idx] title  N rows x M cols` per sheet, exit 0 |
| `tublub -l people.csv` | One bare `N rows x M cols` line — no index/title, nothing to select |
| `tublub -s Users book.xlsx` | Load only `Users`; behaves like a single Dataset (print / `-o` / `-t`) |
| `tublub -s 0,2 book.xlsx` | Print sheets 0 and 2 with heading separators |
| `tublub -s 0,2 -o out.xlsx book.xlsx` | Save those two sheets as a Databook subset |
| `tublub -s 0 one-sheet.xlsx` | Works — a one-sheet workbook still has sheet structure (017) |
| `tublub -s Users people.csv` | Error: input has no sheet structure |
| `tublub -s 2024 budget.xlsx` | Index 2024; out-of-range error suggests `name:2024` if that title exists |
| `tublub --all-sheets book.xlsx` | Print every sheet with heading separators |
| `tublub --all-sheets -o out.xlsx book.xlsx` | Save full Databook (multi-sheet → multi-sheet) |
| `tublub --all-sheets -o out.csv book.xlsx` | Error: format does not support multi-sheet output; pick one sheet with `--sheet` |
| `tublub -o out.xlsx book.xlsx users.csv` | Expand every sheet of every input into `out.xlsx` |
| `tublub --list-formats` | List available formats (was `-l/--list`) |

Single-sheet target formats (csv/tsv/dbf/cli/jira/latex/sql) **never**
auto-split into multiple files. We always require the user to pick a single
sheet.

## Critical files

- `src/tublub/main.py` — all CLI / load / save logic.
- `tests/test_main.py` — extend.
- `tests/conftest.py` — add multi-sheet fixtures (TODO 8).
- `CHANGELOG.md`, `README.md` — user-facing docs (TODO 9).

## Reusable existing pieces

- `try_load_file()` / `try_load_stdin()` — shipped; the "try Databook, fall
  back to Dataset" handshake. All new modes load through these.
- `FormatConfig` / `FORMATS` — keep as-is; still no `databook: bool` (008).
- `filter_args()` — no change needed.
- `save_databook_file()` — the one multi-sheet save path; reuse everywhere.
- `export_databook()` / `_render_databook()` — shipped with TODO 4; the
  multi-sheet export/save/print path TODO 5 reuses for whole-book defaults.
- `_unique_titles()` — takes `(preferred, qualified)` title pairs; keeps the
  preferred title unless it clashes (widened by TODO 6, decision 024).
- `TublubError` boundary — keep the pattern.

---

## TODO 1 — Try-load helper for Databook input — DONE

Shipped in 0.5.0: `load_databook_file`/`load_databook_stdin` and the
`try_load_file`/`try_load_stdin` handshake. See `design.md` § Dataset vs
Databook.

---

## TODO 2 — Flag surface renames (decision 018) — DONE

Shipped (unreleased): `-l` moved to `--list-sheets`, `--list` became the
long-only `--list-formats`, the long format flags are now `-f/--from` and
`-t/--to` (old spellings fail loud), and `--help` lists the formats in its
epilog. `-s` stays reserved for `--sheet` (TODO 4).

---

## TODO 3 — `--list-sheets` reports observed structure (decision 017) — DONE

Shipped (unreleased): inputs with sheet structure print
`[idx] title  N rows x M cols` per sheet (any size, including 1); fallback
Datasets print one bare `N rows x M cols` line — no index, nothing to
select. Empty workbook prints nothing, exit 0. Output shape documented in
`--help`.

---

## TODO 4 — `-s/--sheet` and `--all-sheets`: selection + rendering (decision 017) — DONE

Shipped (unreleased): `-s/--sheet` (0-based index / title / comma-int lists /
repeated occurrences / `name:` escape) and `--all-sheets`, resolved against
observed structure with dedup and selection-order preservation. One selected
sheet renders exactly like a single-sheet input; several render as a
multi-sheet subset through terminal print (`=== title (N rows) ===`
headings), `-o` save, and `-t` export via the attempt-and-catch pattern.
`--all-sheets` on a structureless input is the identity modifier. Extracted
`_render_dataset` / `_format_dataset_as_table` / `export_databook`
(hint-parametrized so the multi-input path never advises the `--sheet` it
rejects); `--tablefmt` now also styles the default stdout table.

---

## TODO 5 — Default mode: whole-book conversion + advice (decision 021) — DONE

Shipped (unreleased): default single-input mode loads once through
`try_load_file` / `try_load_stdin`, so a 2+-sheet input converts whole-book
through `save_databook_file` / `export_databook` with no `--sheet` hint, and
falls back to `sheets()[0]` plus an unconditional stderr data-loss warning
naming `-s` only, on the dedicated `MultiSheetUnsupportedError` — an
undetectable target format, an IO error, or a binary-to-terminal refusal
still propagates. Terminal print shows the first sheet plus a stderr advice
line gated on an injectable `stderr_isatty` threaded from `cli()` (020).
One-sheet workbooks and structureless inputs are unchanged and silent; an
empty workbook keeps the source-naming "No data was loaded from ..." message
(012). Extracted `_render_default` / `_convert_whole_book`. Stdin came along
early, leaving TODO 7 the per-flag rejections only; a size-1 JSON/YAML
*workbook* now renders its sheet instead of a bogus `title`/`data` table.
See decision 023.

---

## TODO 6 — Multi-input expansion — DONE

Shipped (unreleased): `build_databook()` loads each input through
`try_load_file()` and expands every sheet of every input into the output
book. Sheet titles are **kept verbatim** and only clashes are qualified —
a sheet by its workbook stem (`book__Users`), a whole-file sheet by its
parent directory (`hr_people`) — then 015's 31-char clamp and `_2`/`_3`
suffixes as before; `_unique_titles()` now takes `(preferred, qualified)`
pairs. This revises the task's original unconditional `stem__title`
scheme, which would have let a second input rename the first input's
sheets; see decision 023 (021's uniformity rule) and **024**. The
`--sheet`/`--all-sheets` rejection for 2+ inputs shipped with TODO 4 and is
now tested (`TestMultiInputExpansion`). An input contributing no sheets
(empty workbook) makes `_run_databook`'s size-0 exit reachable.

---

## TODO 7 — Stdin support for multi-sheet inputs

**Goal:** `--list-sheets`, `--sheet`, `--all-sheets` work on piped input.

**Tasks**
- `try_load_stdin()` already exists (reads once, tries both
  interpretations) and default mode already routes through it (TODO 5,
  decision 023). Lift the per-flag stdin rejections in
  `_validate_list_sheets` / `_validate_sheet` and route those three flags
  through it too; semantics identical to the file path. `cli()`'s injectable
  `stdin=` edge is already in place for the tests.
- Multi-input mode keeps forbidding `-` (unchanged).

**Tests** — pipe a multi-sheet xlsx into tublub with each flag.

---

## TODO 8 — Tests and fixtures

**Goal:** Cover all the new code paths.

**Tasks**
- `tests/conftest.py` fixtures, built programmatically with tablib:
  `multi_sheet_xlsx`, `multi_sheet_json`, `one_sheet_xlsx`,
  `dup_title_json` (two sheets titled "Users"), `empty_workbook`.
- Per-item test lists above; group as `TestListSheets`, `TestSheetSelect`,
  `TestAllSheets`, `TestHints`, `TestMultiInputExpansion`.

---

## TODO 9 — Docs

**Goal:** User-facing documentation.

**Tasks**
- `CHANGELOG.md` as each item ships: `Added` for `-s/--sheet`,
  `--all-sheets`, expansion, stdin; `Changed` (**breaking**) for the flag
  renames (TODO 2), the `--list-sheets` output shape (TODO 3), and the new
  conversion warning (TODO 5).
- `README.md`: update the flag table, add a "Multi-sheet input" section
  with worked examples, and quote the three rules from the top of this
  file.
- `--help`: short example per new flag; formats epilog (TODO 2).

---

## Future (not scheduled)

- `book.xlsx::Sheet1` per-input selection — the `::` separator stays
  reserved for this (and is why `__` was chosen for expansion titles).
  Unlocks selection in multi-input mode (TODO 6).
- Index ranges (`--sheet 0-4`) — fits the integers-only comma rule.
- `--exclude-sheet NAME` — "everything but the Notes sheet".
- `--list-sheets -t json` machine-readable listing — would lift the
  `--list-sheets`/`-t` mutual exclusion; don't foreclose it, don't build it
  yet.
- **Flatten the test suite to module-level functions.** The `Test*` classes
  add an indentation level and `self` noise without using any class feature
  (no class-scoped fixtures or marks); the pytest-native style is flat
  functions, and the file already carries `# --- section ---` comments that
  can serve as the group separators. Mechanics: dedent, drop `self`, and
  **rename the ~10 leaf names duplicated across classes** (e.g.
  `test_empty_stdin_raises`) — in a flat module a duplicate silently
  *shadows* the earlier definition, so verify the collected count is
  unchanged (`pytest --collect-only -q | tail -1`) before and after. Update
  TODO 8's "group as `TestX`" wording and CLAUDE.md's testing-patterns
  bullet in the same change; do it as a standalone mechanical commit with no
  behavior edits mixed in.
- **`try_load_*` should resolve the input format once.** `try_load_file()`
  calls `load_databook_file()` then `load_dataset_file()`, and each calls
  `_resolve_input_format()`, which re-reads the file to detect and prints
  the "Extension suggests X but content detected as Y" warning
  unconditionally. So a CSV named `data.xls` (decision 004's own example)
  prints that warning **twice** and is read four times. Pre-existing, but
  TODO 5 moved it from the rare `-l`/`-s` paths onto the common default
  path. Both clean fixes change *when* the warning fires — short-circuit
  `_resolve_input_format` when `-f` is given, or have `try_load_*` read and
  detect once and pass the bytes down — so this needs its own decision
  entry. No test currently asserts the double warning; don't add one.

## Open questions

None right now — resolved questions are recorded in
[`decisions.md`](decisions.md) (016-021).

## Verification when each TODO ships

- `just check` (ruff + mypy/ty + pytest) must pass.
- Manual smoke against a real multi-sheet workbook:
  - `tublub --list-formats` and `tublub --help` (epilog)
  - `tublub -l sample.xlsx`; `tublub -l people.csv` (bare line)
  - `tublub -s 0 sample.xlsx`, `tublub -s Users sample.xlsx`
  - `tublub -s 0,2 sample.xlsx` (prints two sheets with headings)
  - `tublub -s 0,2 -o out.xlsx sample.xlsx` (subset round-trip)
  - `tublub -s 2024 budget.xlsx` vs `tublub -s name:2024 budget.xlsx`
  - `tublub --all-sheets sample.xlsx`; `--all-sheets -o out.xlsx`;
    `--all-sheets -o out.csv` (must error, message names `--sheet`)
  - `tublub -o merged.xlsx sample.xlsx extra.csv` (expansion)
  - Data-loss warning: `tublub sample.xlsx -t csv >/dev/null` (warning on
    stderr even when redirected); advice line needs a real TTY.
  - `cat sample.xlsx | tublub -l -` (after TODO 7)
