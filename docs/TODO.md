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
- `_unique_titles()` — widen to accept pre-derived titles (TODO 6).
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

## TODO 5 — Default mode: whole-book conversion + advice (decision 021)

**Goal:** Default mode never drops sheets silently: conversion goes
whole-book when the target can hold it, warn-falls-back to the first sheet
when it can't, and terminal print makes extra sheets discoverable.
(Respec'd 2026-08-04 at the TODO 4 plan review — decision 021 replaced the
original always-first-sheet conversion rule, which was inconsistent with
TODO 6's expand-everything default.)

**Tasks**
- Default single-input mode loads via `try_load_file()` once (no re-read to
  count sheets). On a Databook with `size > 1`:
  - **Terminal print** (no `-o`/`-t`): print `sheets()[0]`; stderr *advice*,
    gated on `sys.stderr.isatty()` (injectable per 020):
    `f"{file}: {size - 1} more sheet(s) — see -l to list, -s to pick, --all-sheets for all"`.
    Advice in a pipe is noise; a TTY gate is the cheap proxy for "a human
    is watching".
  - **Conversion** (`-o` or `-t`): attempt the whole book through the
    TODO 4 helpers (`save_databook_file` / `export_databook`, no hint).
    When the target format cannot hold multiple sheets, fall back to
    `sheets()[0]` via `_render_dataset` with a stderr *data-loss warning*,
    **unconditional**:
    `f"{file}: format {fmt!r} cannot hold all {size} sheets; converting only the first (use -s to choose)"`.
    Dropping sheets is a correctness issue, not advice — scripts must see
    it. The warning suggests `-s` only, never `--all-sheets`, which errors
    in that same situation (explicit flags stay strict; only the default
    falls back). The fallback must trigger only on the multi-sheet-
    unsupported failure — likely a dedicated `TublubError` subclass raised
    by `export_databook`, so unrelated errors (undetectable target format,
    IO) still propagate.
- Size-1 Databook or fallback Dataset: no message, exactly today's
  behavior (mirrors `--all-sheets` semantics per 017/021).
- `--sheet`/`--all-sheets`/`--list-sheets` take other dispatch paths, so
  the messages are naturally suppressed there.

**Tests** — advice present on TTY stderr and absent when piped (injectable
isatty, no monkeypatching); whole-book default: `book.xlsx` + `-o out.json`
/ `-t json` yields all sheets; fallback: `-o out.csv` / `-t csv` emits the
first sheet plus the warning regardless of TTY; unrelated save errors not
swallowed by the fallback; no message for single-sheet inputs or with
`-s`/`--all-sheets`.

---

## TODO 6 — Multi-input expansion

**Goal:** In multi-input mode (`-o` + 2 or more inputs), expand every sheet
of every input into the output Databook.

**Tasks**
- In `build_databook()`, use `try_load_file()` per input: a Databook
  contributes all its sheets titled `f"{path.stem}__{sheet.title}"`; a
  Dataset contributes one sheet titled `path.stem`, as today.
- Generalise `_unique_titles()` to accept pre-derived titles so the
  015 clamp-and-suffix machinery applies uniformly (`stem__title` easily
  exceeds 31 chars).
- **`--sheet`/`--all-sheets` with 2+ inputs: `parser.error` "not supported
  with multiple inputs"** (017). Expansion takes everything; per-input
  selection is deferred to the reserved `book.xlsx::Sheet1` syntax (see
  Future). This replaces the old "apply --sheet uniformly / ignore on
  non-capable inputs" idea, which contradicted single-input strictness.

**Tests** — `tublub -o out.xlsx book.xlsx users.csv` yields book.xlsx's
sheets plus one for users.csv; title collision gets `_2`; long `stem__title`
clamped to 31 chars; `-s`/`--all-sheets` with 2+ inputs rejected.

---

## TODO 7 — Stdin support for multi-sheet inputs

**Goal:** `--list-sheets`, `--sheet`, `--all-sheets` work on piped input.

**Tasks**
- `try_load_stdin()` already exists (reads once, tries both
  interpretations). Lift the per-flag stdin rejections and route through
  it; semantics identical to the file path.
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
