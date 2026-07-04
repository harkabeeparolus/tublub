# TODO — multi-sheet input support

> See [`design.md`](design.md) for the architecture and principles this
> roadmap builds on, and [`decisions.md`](decisions.md) for the decision log.
> Decisions **016–018** define the CLI surface below; 017 supersedes 016's
> single-sheet rejection rule and list format. Respec'd 2026-07-04 after a
> design review; item numbers changed (old TODOs 3/4/5 merged into today's
> TODO 4 — decision 016's "TODO 3" refers to the old numbering).

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
| `tublub book.xlsx out.csv` | Convert first sheet; **always** warn "converting only the first of N sheets" |
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
- `_default_export_handle()` — generalise for Databook stdout export (TODO 4).
- `_unique_titles()` — widen to accept pre-derived titles (TODO 6).
- `TublubError` boundary — keep the pattern.

---

## TODO 1 — Try-load helper for Databook input — DONE

Shipped in 0.5.0: `load_databook_file`/`load_databook_stdin` and the
`try_load_file`/`try_load_stdin` handshake. See `design.md` § Dataset vs
Databook.

---

## TODO 2 — Flag surface renames (decision 018)

**Goal:** Reassign the short flags to the daily operations before the new
modes land, as one coherent breaking release.

**Tasks**
- `--list` → `--list-formats`, long-only. Rename dest `list` →
  `list_formats`; it is referenced in `cli()`, `_validate_args`,
  `_validate_list_sheets`, and `_should_use_implicit_stdin`.
- Move `-l` to `--list-sheets`. Keep **no** `--list` alias: argparse's
  default prefix matching makes bare `--list` error "ambiguous option:
  could match --list-formats, --list-sheets" — that *is* the migration
  message, so don't set `allow_abbrev=False`.
- Replace the long forms: `-f/--from` and `-t/--to` (pandoc vocabulary);
  drop `--in-format` and `--format` entirely — both fail loud as
  unrecognized arguments, and the short flags are untouched. Keep the
  explicit `dest="in_format"`/`dest="out_format"` (`from` is a Python
  keyword, so argparse must not derive the dest from the flag name).
- Add `-s` to `--sheet` when TODO 4 creates it (recorded here so the short
  flag stays reserved).
- Append the dynamic format list to the parser epilog
  (`epilog=f"available formats: {' '.join(get_formats())}"`), so `--help`
  answers the discovery question; `--list-formats` remains for scripting.
- `CHANGELOG.md`: Changed entries marked **breaking**.

**Tests** — `parse_command_line` cases for each rename; `--from`/`--to` set
`in_format`/`out_format`; dropped spellings (`--list`, `--in-format`,
`--format`) are rejected; bare `tublub -l` errors "requires an input file";
`--list-formats` rejects filenames (existing `--list` test, renamed).

---

## TODO 3 — `--list-sheets` reports observed structure (decision 017)

**Goal:** Make `--list-sheets` output exactly mirror what `--sheet` accepts.

**Tasks**
- `try_load_file()` returned a **Databook** (any size, including 1): print
  `f"[{idx}] {sheet.title}  {len(sheet)} rows x {ncols} cols"` per sheet.
  The size-1 index is a true affordance under 017 — `--sheet 0` works.
- Returned a fallback **Dataset** (CSV / records-shaped JSON): print one
  bare `f"{len(ds)} rows x {ncols} cols"` line — no index, no title. The
  missing `[idx]` visually teaches that there is nothing to select. This
  replaces both the 0.5.0 `[0] {stem}` line and 016's title-only form.
- Empty workbook: print nothing, exit 0 (unchanged).
- No `_sheets_of()` normaliser needed: both this and TODO 4 branch on
  Databook-ness directly, which is the 017 rule itself.
- Document the output shape in `--help`.

**Tests** — multi-sheet xlsx (indexed lines), one-sheet xlsx (`[0] Title`),
csv (bare line), records-shaped json (bare line), empty workbook, existing
mutual-exclusion tests unchanged.

---

## TODO 4 — `-s/--sheet` and `--all-sheets`: selection + rendering (decision 017)

**Goal:** Pick sheets by index or title, or all of them, and render the
result through every existing output mode. Merges old TODOs 3/4/5.

### Argparse & validation

- `-s/--sheet SEL`, `action="append"`, default `None`; `--all-sheets`,
  `store_true`. Mutually exclusive with each other and with
  `--list-formats`/`--list-sheets`.
- Cook occurrences into `args.sheets: list[str]`: an occurrence is
  comma-split **only when every comma-piece is an integer** (after strip);
  otherwise it is one literal title token ("Revenue, EMEA" stays whole).
  An empty occurrence or piece (`--sheet ,`, `--sheet ""`) is a usage error
  ("no sheet selector given").
- `_validate_sheet` mirroring `_validate_list_sheets`: single local file
  only in this increment — reject stdin (TODO 7) and 2+ inputs (TODO 6
  rejects them permanently).

### Resolution (per token, against `book.sheets()`)

- `name:REST` → forced title match on REST (strip exactly one `name:`; a
  literal title starting with `name:` needs the prefix doubled).
- Integer token → 0-based index, **always** (016). Out of range →
  `TublubError` "sheet index N out of range (0-M)"; if some sheet's title
  equals the token, append "for the sheet titled 'N' use --sheet name:N".
  Never fall back from index to title.
- Anything else → title match: exact, then case-insensitive. Multiple hits
  at either stage (duplicate titles are legal in JSON/YAML books) → error
  listing the candidate indices. No hit → error listing all titles; if the
  token contains a comma, add "repeat --sheet to select multiple sheets by
  name".
- Title matching skips empty titles; index selection reaches everything.
- Empty workbook → "workbook has no sheets".
- Structure gate: input loaded as a fallback Dataset → "input has no sheet
  structure" (observational, 008-safe). Applies to `--sheet` only —
  `--all-sheets` names no specific structure, so on a structureless input
  it is the identity modifier (plain single render, old TODO 4's
  "no special-casing" kept).

### Dispatch & rendering (`_run_sheets`)

- Load via `try_load_file()`; resolve tokens; dedup by resolved index,
  keeping first occurrence, preserving selection order. `--all-sheets` =
  select every index, same path from here on.
- **1 sheet selected** → `_render_dataset(ds, args, extra_args)`, extracted
  from the tail of `_run_single` (save to `-o` / export via `-t` / print),
  so selection reuses the real renderer and can't drift.
- **N sheets selected** → build a fresh Databook from the subset, then:
  - `-o FILE` → `save_databook_file()`. Refine its UnsupportedFormat
    message to "...does not support multi-sheet output; pick one sheet
    with --sheet".
  - `-t FMT` (no `-o`) → attempt `book.export(fmt)`, catch
    `UnsupportedFormat` with the same message; route bytes/str through a
    Databook-aware `_default_export_handle` (binary to a pipe is fine,
    binary to a TTY refuses, as today).
  - neither → `print_databook(book)`:

    ```
    === <title> (<N> rows) ===
    <tabulated sheet, honouring --tablefmt>

    ```
    One blank line between sheets, none after the last; empty sheets still
    get a heading. Extract `_format_dataset_as_table(ds)` shared with the
    single-Dataset print path.

**Tests** — pick by name / index / comma-int list; "0,Users" treated as one
literal title (miss lists titles); repeated `-s`; selection order preserved;
duplicates deduped; `name:` forced title; `name:2024` vs index 2024 plus the
error hint; duplicate-title ambiguity errors with indices; case-insensitive
ambiguity (`users` + `USERS` vs `Users`); unknown name lists titles;
out-of-range; empty workbook message; empty-string titles selectable by
index only; csv and records-json rejected ("no sheet structure"); size-1
xlsx selectable by `0` and by title; multi-select terminal print layout;
multi-select `-t json` to stdout; multi-select `-o out.xlsx` round-trip;
multi-select `-o out.csv` errors with advice; `--all-sheets` on csv is a
plain render; `--all-sheets` print/save/export; mutual exclusions; stdin and
multi-input rejection.

---

## TODO 5 — Advice vs data-loss warning in default mode

**Goal:** Make extra sheets discoverable, and never drop them silently.
These are two different messages (design review, 2026-07-04).

**Tasks**
- Default single-input mode loads via `try_load_file()` once (no re-read to
  count sheets). On a Databook with `size > 1`, take `sheets()[0]` and:
  - **Terminal print** (no `-o`/`-t`): stderr *advice*, gated on
    `sys.stderr.isatty()`:
    `f"{file}: {size - 1} more sheet(s) — see -l to list, -s to pick, --all-sheets for all"`.
    Advice in a pipe is noise; a TTY gate is the cheap proxy for "a human
    is watching".
  - **Conversion** (`-o` or `-t`): stderr *data-loss warning*,
    **unconditional**:
    `f"{file}: converting only the first of {size} sheets (use -s to choose, --all-sheets for all)"`.
    Dropping sheets is a correctness issue, not advice — scripts must see
    it.
- Size-1 Databook or fallback Dataset: no message.
- `--sheet`/`--all-sheets`/`--list-sheets` take other dispatch paths, so
  the messages are naturally suppressed there.

**Tests** — hint present on TTY stderr and absent when piped (monkeypatch
`isatty`); conversion warning present regardless of TTY for both `-o` and
`-t`; no message for single-sheet inputs or with `-s`/`--all-sheets`.

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
[`decisions.md`](decisions.md) (016-019).

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
