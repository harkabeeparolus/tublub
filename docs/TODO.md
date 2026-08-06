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

## Don't clobber an existing output file silently — DONE

Shipped (unreleased): `-y/--yes` and `-n/--no-clobber`, plus a default that
asks at a terminal (question on stderr, default no) and refuses anywhere
else. Decision 025 settles the two questions the sketch left open, in both
cases against its own leaning: the non-terminal default refuses rather than
overwriting — the accident that prompted this was an agent, and an agent is
not a terminal, so a prompt-only guard would have caught nothing — and every
refusal exits non-zero rather than treating "nothing to do" as success.

## A failed multi-sheet save leaves the output file empty — DONE

Shipped (unreleased): `save_databook_file` renders the workbook into memory
and only then opens the output, so a format that cannot hold the sheets leaves
the file untouched. Decision 026 supersedes the sketch's mechanism — book
capability cannot be decided before opening, because an empty
`Databook().export()` raises `IndexError` for xls/xlsx rather than
`UnsupportedFormat`, so the real export has to be attempted (008) and buffered.
The sketch's ban on temp-file-and-rename stands.

## `try_load_*` should resolve the input format once

`try_load_file()` calls `load_databook_file()` then `load_dataset_file()`,
and each calls `_resolve_input_format()`, which re-reads the file to detect
and prints the "Extension suggests X but content detected as Y" warning
unconditionally. So a CSV named `data.xls` (decision 004's own example)
prints that warning **twice** and is read four times. Pre-existing, but the
0.6.0 whole-book default moved it from the rare `-l`/`-s` paths onto the
common default path. Both clean fixes change *when* the warning fires —
short-circuit `_resolve_input_format` when `-f` is given, or have
`try_load_*` read and detect once and pass the bytes down — so this needs
its own decision entry. No test currently asserts the double warning; don't
add one.

## Title a single-input sheet after its input file

`tublub customers.csv out.xlsx` writes a sheet named `Tablib Dataset` —
Tablib's fallback when `Dataset.title` is `None`, which the single-input
path never sets. Only `build_databook()` assigns titles, so
`-o out.xlsx a.csv b.csv` names the sheets `a`/`b` while
`-o out.xlsx a.csv` names the one sheet `Tablib Dataset`: dropping the
second input changes how the *first* is named, the same arity surprise
021/024 outlawed for how inputs are *read*. Sketch: in the single-input
save/export path, title the sheet `path.stem` (through `_fit_title` for
the 31-char cap) **only when the input had no sheet structure** — an
observed sheet title must survive verbatim per 024, which it does today
(a one-sheet workbook already round-trips its real title). Visible only
in formats that carry sheet names (xlsx/ods/xls); records-shaped
json/yaml and the single-sheet text formats are unaffected, so it is not
a breaking output change for them. Open question for whoever ships it:
stdin has no stem — keep Tablib's fallback, or name it `stdin`?

## Smaller multi-sheet extensions

- `book.xlsx::Sheet1` per-input selection — the `::` separator stays
  reserved for this (and is why `__` was chosen for expansion titles).
  Unlocks selection in multi-input mode.
- Index ranges (`--sheet 0-4`) — fits the integers-only comma rule.
- `--exclude-sheet NAME` — "everything but the Notes sheet".
- `--list-sheets -t json` machine-readable listing — would lift the
  `--list-sheets`/`-t` mutual exclusion; don't foreclose it, don't build it
  yet.
