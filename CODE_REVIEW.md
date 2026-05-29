# Code Review — pre-release workshop items

Findings from a pre-release scan of `src/tublub/main.py` and tests. Each
item is framed as a TODO so we can pick it up cold and workshop the
trade-offs in a future session. They are independent — work them in any
order, or drop any that we decide aren't worth the churn.

Cross-reference: `TODO.md` covers the multi-sheet feature roadmap. The
items below are orthogonal polish/refactor work. Where a TODO.md item
touches the same code, the cross-reference is noted inline.

## Status summary

All actionable findings are resolved. Priority A/B landed in earlier
commits; C1-C4, D1, D2, E2 landed together as internal cleanup (no
behavior change); E1 is WONTFIX; the F-series are decisions, now recorded
inline.

| Finding | Status |
|---------|--------|
| CR-A1, A2, A3 | DONE (earlier commits) |
| CR-B1, B2, B3 | DONE (earlier commits) |
| CR-C1, C2, C3, C4 | DONE |
| CR-D1 | DONE (resolved by C3) |
| CR-D2 | DONE |
| CR-E1 | WONTFIX (style, not worth the diff) |
| CR-E2 | DONE |
| CR-F1, F2, F3 | DECIDED (no change) |

---

## Priority A — architectural questions worth a real conversation

These shape what the next chunk of feature work looks like. Best decided
*before* TODO 3–8 land, because those items multiply the affected code.

### CR-A1 — Dataset vs Databook: parallel paths everywhere

**Status: DONE** — `try_load_file`/`try_load_stdin` now encapsulate the
fallback handshake (status-quo + helper direction).

**Where:** `load_dataset_file` / `load_databook_file`,
`load_dataset_stdin` / `load_databook_stdin`, `save_dataset_file` /
`save_databook_file`, `_run_databook` vs the single-input branch in
`cli()`.

**State:** Every load/save operation has two flavours. The "try Databook,
fall back to Dataset" pattern is replicated in `_run_list_sheets` and
will repeat in TODO 6 (stderr hint) and TODO 8 (stdin multi-sheet).

**Why it matters:** The TODO roadmap adds at least three more code paths
(`--sheet`, `--all-sheets`, multi-input expansion) that each need to
decide Dataset-vs-Databook. Without an abstraction, each new flag is
two implementations and a coordination point.

**Possible directions to workshop:**
- **Unify on Databook internally.** A single-sheet input becomes a
  1-sheet Databook; the renderer/saver decides at the boundary. Costs:
  changes the type signature of most helpers; some tablib ops differ
  between Dataset and Databook.
- **Introduce a `LoadedInput` wrapper** with `.sheets()` and `.first()`
  methods that abstracts over both. Cheaper than a full unify, but
  yet-another-type.
- **Status quo + helper for the fallback pattern.** Keep the two types,
  but extract `try_load(path) -> Databook | Dataset` so call sites stop
  re-implementing the `if book is None: dataset = ...` dance.

---

### CR-A2 — `cli()` dispatch is implicit mode detection

**Status: DONE** — `cli()` is now a flat four-way switch with per-mode
`_run_*` helpers.

**Where:** `src/tublub/main.py:58-102`.

**State:** Mode is inferred from flag combinations: `args.list`,
`args.list_sheets`, `len(args.infiles) >= 2`, then "default single-input".
With TODO 3 (`--sheet`), TODO 4 (`--all-sheets`), and TODO 7 (multi-input
expansion) the dispatcher grows more conditions.

**Why it matters:** Approaching the C901/PLR0912 caps. Each new mode adds
another `if` plus a validation rule in `_validate_args`. The relationship
between modes (which are mutually exclusive, which compose) is encoded
across two files and a growing pile of `parser.error()` calls.

**Possible directions to workshop:**
- **Explicit `Operation` enum** set during `parse_command_line` (e.g.
  `LIST_FORMATS / LIST_SHEETS / DATABOOK_OUT / SINGLE / ALL_SHEETS`);
  `cli()` becomes a dispatch table.
- **Sub-command split** via argparse subparsers — bigger change, but
  cleaner help output and per-mode validation.
- **Status quo + keep extracting `_run_*` helpers** as we have for
  `_run_list_sheets` and `_run_databook`.

---

### CR-A3 — Input state is fragmented across three Namespace attrs

**Status: DONE** — `args.infile` dropped; `args.infiles` + `args.stdin`
are the only input state. (Also settles CR-F3.)

**Where:** `parse_command_line`, line 484-486 sets `args.infile`,
`args.outfile`, `args.infiles`; `args.stdin` is set earlier.

**State:** Four attributes describe "what input we're reading":
`args.infile: Path | None`, `args.infiles: list[Path]`, `args.stdin: bool`,
plus the implicit "no inputs and not TTY" branch on line 481. Invariants
(e.g. `stdin → infile is None and infiles == []`) live in code comments
and reader's heads.

**Why it matters:** When TODOs 7–8 add per-file Databook expansion and
stdin multi-sheet, the invariants get harder to keep straight.

**Possible directions to workshop:**
- **Single `InputSpec` dataclass** with `paths: list[Path]` and
  `from_stdin: bool` (plus `is_multi` property). Build it in
  `_reconcile_positionals`; `cli()` reads from it.
- **Keep `args.infiles` as the only truth**, drop `args.infile` (always
  `infiles[0] if infiles else None` at call sites). Less code change,
  retires one redundant field.

---

## Priority B — correctness / bugs

### CR-B1 — Dead guard in `export_dataset`

**Status: DONE** — guard removed; `_default_export_handle` has a narrow
return type so the type checker needs no appeasement.

**Where:** `src/tublub/main.py:414-416`.

```python
if file_handle is None:  # Catch type warning for Pylance
    msg = "No output stream available for export"
    raise TublubError(msg)
```

**State:** Genuinely unreachable. The branches above either assign
`file_handle` or raise. The comment is honest; the code is type-checker
appeasement.

**Why it matters:** Dead code drift. If lint/type-check tooling changes,
this will rot.

**Possible directions to workshop:**
- Restructure so the type checker can narrow without the guard (e.g.
  return early in the binary-TTY branch, then assign `file_handle =
  sys.stdout.buffer if is_bin(...) else sys.stdout` once).
- Use `typing.cast` or `assert file_handle is not None` (cheaper).
- Leave it and add `# pragma: no cover`.

---

### CR-B2 — Broad exception catch in `load_databook_*`

**Status: DONE** — accepted as a deliberate choice; regression tests
confirm corrupt JSON surfaces as a real error, not silent fallback.

**Where:** `src/tublub/main.py:202-203` and `:284-285`.

```python
except (tablib.UnsupportedFormat, KeyError, TypeError):
    return None
```

**State:** Already a deliberate choice — documented in both the function
docstring and `TODO.md`'s "Don't hard-code a Tablib capability matrix"
section. The `KeyError`/`TypeError` cases catch shape-mismatched
JSON/YAML records.

**Why it matters:** `KeyError`/`TypeError` are broad. If tablib ever
raises one for a genuinely corrupt file inside the load path, we'll
silently treat the file as "not a Databook" and try the Dataset path —
which may then succeed with garbage, or fail with a confusing message.

**Possible directions to workshop:**
- Narrow via inspection of the exception message/source (fragile,
  couples us to tablib internals).
- Probe with a content sniff first (e.g. `json.loads` for `fmt == "json"`)
  before calling `tablib.Databook().load`, so we only catch
  `UnsupportedFormat`.
- Accept the current behaviour and add a regression test that exercises
  a corrupt JSON to confirm it surfaces as a useful error, not silent
  fallback.

---

### CR-B3 — `_unique_titles` collides on stem regardless of directory

**Status: DONE** — parent-dir qualifies the title on stem collision
(`data_a`, `backup_a`), with the numeric suffix as final fallback and a
stderr note on any disambiguation.

**Where:** `src/tublub/main.py:387-396`.

**State:** `tublub -o out.xlsx data/a.csv backup/a.csv` produces sheets
`a` and `a_2`, losing the directory disambiguation that the user almost
certainly intended.

**Why it matters:** Quiet behaviour. No warning is printed. The user
discovers it on opening the workbook.

**Possible directions to workshop:**
- Print a stderr note when a collision is suffixed.
- On collision, fall back to a longer disambiguator (parent dir + stem).
- Document the behaviour in `--help` and leave as-is.

**Cross-ref:** Touched by TODO 7 (sheet titles from multi-sheet inputs);
worth resolving the policy before that lands.

---

## Priority C — DRY / repetition

### CR-C1 — Format detection logic duplicated for file vs stdin

**Status: DONE** — extracted `_detect_format_from_bytes(raw)`; both
`detect_format_from_file` and `_read_and_detect_stdin` call it.

**Where:** `detect_format_from_file` (`:246-257`) and the inner block of
`_read_and_detect_stdin` (`:303-316`).

**State:** Identical fallback chain: binary detect → text decode → text
detect → `_looks_like_text_lines` heuristic. The file version starts
from a path; the stdin version starts from already-read bytes.

**Possible directions to workshop:**
- Extract `_detect_format_from_bytes(raw: bytes) -> str | None` and have
  both functions call it.
- Inline-document why they can't share; if there's no reason, refactor.

---

### CR-C2 — Output format resolution duplicated across save helpers

**Status: DONE** — extracted `_resolve_output_format(force, path)`; both
savers call it.

**Where:** `save_dataset_file` (`:331-334`) and `save_databook_file`
(`:366-369`).

```python
file_format = force_format or guess_file_format(file_name)
if file_format is None:
    msg = f"Unable to detect target file format for: {file_name}"
    raise TublubError(msg)
```

**Possible directions to workshop:**
- Extract `_resolve_output_format(force, path) -> str` that raises on
  None. Both savers call it.

---

### CR-C3 — Format-validity check duplicated in `_validate_args`

**Status: DONE** — extracted `_check_known_format(parser, fmt, label)`;
the two distinct error messages are preserved. (Also resolves CR-D1.)

**Where:** `src/tublub/main.py:563-569`.

**State:** Two near-identical branches for `args.out_format` and
`args.in_format`, each building the formats list and an error message.

**Possible directions to workshop:**
- Extract `_check_known_format(parser, fmt, kind)` (kind = "input"/
  "output"). Removes the duplicate `get_formats()` mention and unifies
  the message template.

---

### CR-C4 — Newline plumbing repeated at every open site

**Status: DONE** — extracted `_open_for_format(path, cfg, *, write)`; the
four open sites now call it instead of reaching into `cfg.open_kwargs`.

**Where:** `:165, :168, :194-195, :198, :337-338, :380-381`.

**State:** Pattern: `newline = cfg.open_kwargs.get("newline")` then
`file_name.open(mode, newline=newline)`. Only CSV actually sets a
non-default newline; the dance happens for every format.

**Possible directions to workshop:**
- Helper `_open_for_format(path, fmt, mode) -> ContextManager[IO]` so
  callers stop reaching into `cfg.open_kwargs`.
- Or accept it as too small to abstract — 2 lines per site, 3 sites.

---

## Priority D — complexity / function size

### CR-D1 — `_validate_args` is near the C901 cap and growing

**Status: DONE** — resolved as a side effect of CR-C3; pulling the two
format checks into `_check_known_format` dropped the branch count well
under the cap. Revisit when TODO 3/4 flags land.

**Where:** `src/tublub/main.py:548-569`.

**State:** Already at multiple-branch territory; TODOs 3 and 4 add
mutual-exclusion rules and per-flag validation. CLAUDE.md flags this
function by name as a refactor candidate.

**Possible directions to workshop:**
- Extract a per-flag validator (`_validate_list_sheets` is already in
  this shape); add `_validate_sheet_selection`, `_validate_all_sheets`
  as siblings as those flags land.
- Or table-driven mutual-exclusion rules.

---

### CR-D2 — `parse_command_line` does five things

**Status: DONE** — extracted `_collect_extra_args(args)` (and
`_should_use_implicit_stdin` per CR-E2); `parse_command_line` now reads as
a short orchestration.

**Where:** `src/tublub/main.py:464-500`.

**State:** Parses argv → reconciles positionals → detects stdin →
validates → extracts extra_args. Each step is short, but the function
holds the lot.

**Possible directions to workshop:**
- Split: `parse_command_line` orchestrates; the stdin detection and
  extra-args extraction become standalone helpers.
- Status quo if we judge the current size acceptable.

---

## Priority E — non-Pythonic / style

### CR-E1 — `_unique_titles` uses manual dict counting

**Status: WONTFIX** — style preference; current code is readable and the
diff isn't worth it (matches the verdict below).

**Where:** `src/tublub/main.py:387-396`.

**State:** Loop with `counts.get(stem, 0) + 1`. `collections.Counter`
would do the same job; `defaultdict(int)` likewise.

**Verdict:** Style preference. Current code is readable; replacement may
not be worth the diff. Worth a one-minute decision, not a debate.

---

### CR-E2 — Implicit stdin detection is easy to misread

**Status: DONE** — extracted `_should_use_implicit_stdin(infiles, args)`
with a docstring explaining the pipe-vs-TTY reasoning.

**Where:** `src/tublub/main.py:481`.

```python
elif not infiles and not args.list and not sys.stdin.isatty():
    args.stdin = True
```

**State:** The `not sys.stdin.isatty()` clause silently switches modes
when piped. Correct but the intent isn't obvious at a glance.

**Possible directions to workshop:**
- Extract `_should_use_implicit_stdin(args) -> bool` with a docstring.
- Add a single-line comment above.

---

## Priority F — open questions to confirm (no change needed, just decide)

### CR-F1 — Mismatch warning for extension vs detected format

**Where:** `_resolve_input_format`, `:219-223`. Currently prints to
stderr and proceeds with `detected`. Is "warn and continue" the right
policy, or should `-f` be required when the mismatch happens?

**Decided: keep warn-and-continue.** `-f` is the explicit override; hard
-failing on a mismatch would be hostile to the common case (legacy
exports with wrong extensions, which is exactly why we trust content over
extension). No change.

### CR-F2 — Empty-input parity

**Where:** `cli()` `:83-85` (`if not my_data: sys.exit(...)`) vs
`_run_databook` `:133-134` (`if book.size == 0: sys.exit(...)`).
Slightly different error messages and triggering conditions. Confirm
this is intentional or unify the wording.

**Decided: leave as-is.** The two paths genuinely differ — single-input
reports the source it read from, the databook path reports across all
inputs — so the distinct messages carry real information. No change.

### CR-F3 — `args.stdin` placement

`args.stdin` is set inside `parse_command_line` (not by argparse).
Confirm we want this — alternative is `args.stdin` lives only on the
`InputSpec` proposed in CR-A3 and never on `args`.

**Decided: keep on `args`.** CR-A3 chose `args.infiles` + `args.stdin` as
the input state rather than a separate `InputSpec`, so this is settled.
No change.

---

## How to workshop these

When picking one up:

1. Re-read the relevant section of `src/tublub/main.py` — the file is
   small enough to hold in head.
2. Decide between the options listed (or invent a better one).
3. If the change is non-trivial, sketch the diff before implementing.
4. `just check` after each item.
5. Update `CHANGELOG.md` only if user-visible behaviour changes (most of
   these are internal).
