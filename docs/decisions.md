# Decisions

Append-only log of design decisions and their rationale — the "why we did it
this way" that isn't recoverable from the code. Oldest first, newest at the
bottom. For the living design overview see [`design.md`](design.md).

Re-founded 2026-05-29 from the git history, so the early entries carry their
true (often much older) dates and cite the commits they came from. Henceforth
this log is append-only: don't edit past entries; if a decision is reversed,
add a new entry that supersedes it. Entries from before the 2026 agent-era
commits have terse commit messages, so their rationale is drawn from the
commit, the CHANGELOG, and the surrounding code — noted as inferred only
where genuinely so.

---

### 000. Encode Tablib's per-format file-open rules in code — why tublub exists
*2022-07-26 · Accepted*

**Context.** Tablib supports many tabular formats for parsing and
serialization, but it does not itself know how to *open the files on disk* for
each format — whether a format needs binary or text mode, how newlines must be
handled, and so on. At the time, that knowledge lived only in Tablib's web
documentation, spelled out per format. A tool that wanted to use Tablib for
file I/O therefore couldn't lean on Tablib's code for the open step; it had to
go read the online docs for every format it meant to support.

**Decision.** Build tublub as a thin wrapper that puts the file-open knowledge
into actual Python code. The `FORMATS` / `FormatConfig` table carries, per
format, whether it is binary and what open kwargs (e.g. `newline`) it needs,
so loading and saving each format to disk just works without consulting the
docs.

**Why.** This gap is the project's reason for existing: encoding the
per-format open rules once, in code, is the core value tublub adds on top of
Tablib. (Initial commits `53c48c6` / `0576ec6`; the knowledge now lives in the
`FORMATS` table — see decision 002 for its structure, and
[`design.md` Future directions](design.md) for ways this could be solved more
fundamentally upstream.)

---

### 001. Depend on Tablib's file-format extras only (no Pandas)
*2022-07-29 · Accepted*

**Context.** tublub's job is converting files between formats. It first
depended on `tablib[all]`, which pulls in Pandas. Pandas turned out to be a
DataFrame bridge for use *from Python code*, not a file format tublub can read
or write.

**Decision.** Depend on an explicit list of Tablib's *file-format* extras —
currently `tablib[cli,html,ods,xls,xlsx,yaml]` — and exclude any extra that
exists for developers manipulating data in Python (Pandas being the case in
point). The selection rule is forward-looking: when Tablib changes its extras,
judge each one by a single test — *is it a file format?* If yes, add it; if
it's for in-code data handling, leave it out.

**Why.** A DataFrame is not a file format, so a format-conversion CLI has no
use for one, and dropping it reduces the installed size on disk (CHANGELOG
`[0.3.0]`). Tying the dependency set to "file formats only" keeps tublub's
scope and its install footprint aligned with what it actually does. (Commit
`632da50`, CHANGELOG `[0.3.0]`, pyproject `tablib[...]` extras.)

---

### 002. A single `FORMATS` / `FormatConfig` table
*2026-02-09 · Accepted*

**Context.** Per-format knowledge was spread across four parallel dicts
(`BINARY_FORMATS`, `LOAD_EXTRA_ARGS`, `SAVE_EXTRA_ARGS`, `OPEN_EXTRA_ARGS`),
so adding or changing a format meant editing several places in sync.

**Decision.** Collapse them into one `FORMATS: dict[str, FormatConfig]`, where
each `FormatConfig` holds `binary?`, allowed load/save kwargs, and open kwargs.
Adding or tweaking a format is a single-entry edit.

**Why.** One source of truth per format; call sites (`filter_args`,
`_open_for_format`) read from it instead of branching on format themselves.
(Commit `dd1f64d`.)

---

### 003. Library helpers raise `TublubError`; only `cli()` exits
*2026-02-09 · Accepted*

**Context.** Helpers called `sys.exit()` directly, which made them untestable
and coupled them to the CLI.

**Decision.** Helpers raise `TublubError(ValueError)`; only the CLI edge
(`cli()` / the `_run_*` entry points) catches it and converts to
`sys.exit(msg)`. For type narrowing, use explicit `if x is None: raise
TublubError(...)` or a narrow-return helper rather than `assert`/`cast`.

**Why.** Keeps every helper testable and reusable outside the CLI, and keeps
the exit-the-process decision at one boundary. (`assert` is also banned in
`src/` by S101.) (Commit `e5a7e3b`.)

---

### 004. Content-first format detection, single-column heuristic, and `-f`
*2026-02-09 · Accepted*

**Context.** A file's extension and its actual content can disagree, and
neither is fully reliable on its own.

**Decision.** Resolve input format as `-f` flag > content detection >
extension. Detect from content with a binary pass then a text pass
(`_detect_format_from_bytes`), and as a last resort treat
no-delimiter plain-text lines as TSV (`_looks_like_text_lines`, rejecting
text with `,\t;|` to avoid misdetecting prose). On an extension/content
mismatch, warn to stderr and proceed with the detected format.

**Why.** Extensions lie (legacy exports use `.xls` for CSV), so content wins —
this inverted the earlier 2024 behaviour that only fell back to the suffix
when Tablib failed (`0ad07b3`). But `csv.Sniffer` can't sniff single-column
CSV/TSV, so `-f` is the explicit escape hatch and the heuristic catches the
common single-column case (TSV over CSV so comma-bearing values aren't split).
Hard-failing on a mismatch would be hostile to the wrong-extension case; the
warning makes the ambiguity visible without blocking — that warn-and-continue
policy was reconfirmed 2026-05-29. (Commits `7b22d46`, `9f849ab`, `d9b7c1d`;
prior art `0ad07b3`.)

---

### 005. argparse `store_const` + `default=None` so flag defaults don't leak
*2026-02-09 · Accepted*

**Context.** Boolean flags like `--no-headers` / `--no-xlsx-optimize` used
`store_false`, which injected their argparse default (`True`) into
`extra_args` on *every* invocation — silently passing kwargs to Tablib the
user never asked for.

**Decision.** Use `action="store_const", const=False, default=None` for those
flags, and only forward args whose value is not `None`
(`filter_args` / `_collect_extra_args`). A flag the user didn't pass stays
`None` and never reaches Tablib.

**Why.** "User didn't set it" must be distinguishable from "user set it to the
default"; only explicit flags should alter behaviour. Easy to regress — worth
recording. (Commit `9f849ab`, bug #3.)

---

### 006. Project baseline: Python >=3.10, uv build, Justfile
*2026-02-09 · Accepted*

**Context.** Modernizing the 2022 codebase and its tooling.

**Decision.** Target Python >=3.10 (`requires-python = ">=3.10"`), build with
`uv_build`, and drive lint/typecheck/test/run through a `Justfile`
(`just check` = ruff + mypy + ty + pytest).

**Why.** 3.10 unlocks modern typing syntax (`X | None`, etc.) used throughout;
uv + just give one fast, reproducible entry point for builds and the dev loop.
(Commits `8f0c258`, `00ac167`, `297ac23`.)

---

### 007. Multi-input -> multi-sheet Databook output via `-o`
*2026-04-27 · Accepted*

**Context.** tublub handled one input -> one output; there was no way to
combine several inputs into a single workbook.

**Decision.** With two or more inputs and `-o/--output`, build a multi-sheet
`tablib.Databook` (XLSX/ODS/JSON/YAML/...). Sheet titles default to each
input's file stem, with `_2`/`_3` suffixes on collision (`_unique_titles`).
Single-input behaviour is unchanged.

**Why.** This introduced the Dataset-vs-Databook split that later load-side
work builds on, and established that multi-sheet output is opt-in via `-o`
rather than implicit. (Commit `903beb3`.)

---

### 008. No static Tablib capability matrix; discover by attempting + catching
*2026-04-29 · Accepted*

**Context.** Only some formats support multi-sheet (Databook) load/save. We
need to know which, per operation.

**Decision.** Never hard-code a `{format: supports_databook}` table and never
add a `databook: bool` to `FormatConfig`. Attempt the Databook operation and
catch failure — `tablib.UnsupportedFormat` plus `KeyError`/`TypeError`,
returning `None` to mean "fall back to Dataset". `save_databook_file` mirrors
this on the export side.

**Why.** A static table would drift from upstream and force a tublub change
every time Tablib gains a format. `KeyError('title')`/`TypeError` are included
because Tablib raises them when a Databook-capable format (JSON/YAML) holds a
single-Dataset shape — a records list like `[{"name": "Alice"}, ...]` rather
than `[{"title": ..., "data": [...]}, ...]` — which would otherwise crash
`load_databook_*` on every plain `records.json`. The catch is scoped to the
capability question; genuine load errors (corrupt files, decode failures)
still propagate. (Commits `79fdef1`, `669815c`.)

---

### 009. Input state is `args.infiles` + `args.stdin`, not an `InputSpec`
*2026-05-28 · Accepted*

**Context.** Input state had drifted across several Namespace attributes
(`infile`, `infiles`, `stdin`), with invariants living only in comments.

**Decision.** `args.infiles: list[Path]` and `args.stdin: bool` are the only
input-state truth. Dropped the singular `args.infile`. `args.stdin` is set in
`parse_command_line` (not by argparse) and kept on `args` rather than moved to
a separate `InputSpec` dataclass.

**Why.** Two fields are easy to keep consistent; a wrapper type was more
machinery than the size of the problem warranted. (Commit `44b2252`.)

---

### 010. `cli()` is a flat dispatch over explicit modes
*2026-05-28 · Accepted*

**Context.** Mode used to be inferred from flag combinations scattered through
`cli()`, approaching the C901/branch caps.

**Decision.** `cli()` is a flat switch (list / list-sheets / databook /
single), one `_run_*` per mode. New modes add a branch plus a `_run_*`;
mutual-exclusion rules go in per-flag `_validate_*` helpers. Did not adopt
argparse subparsers.

**Why.** Keeps the dispatcher readable and each mode independently testable
without the bigger surface change subparsers would impose. (Commit `10a1ea2`.)

---

### 011. `try_load_*` fallback handshake instead of unifying on Databook
*2026-05-28 · Accepted*

**Context.** Every load path had to decide Dataset vs Databook, and the
roadmap multiplies those paths.

**Decision.** Keep both Tablib types; extract `try_load_file` /
`try_load_stdin` helpers that try Databook and fall back to Dataset, so call
sites stop reimplementing the dance. Did *not* unify everything onto Databook
internally.

**Why.** A helper for the fallback was far cheaper than changing the type
signature of most helpers, and some Tablib ops differ between the two types.
The stdin variant must try both interpretations on one read (stdin is
consume-once). (Commit `10a1ea2`.)

---

### 012. Keep the two empty-input messages distinct
*2026-05-29 · Accepted*

**Context.** The single-input and multi-input paths report "no data" with
different wording and triggers (`not my_data` vs `book.size == 0`).

**Decision.** Leave them distinct.

**Why.** They genuinely differ — single-input names the source it read from;
the Databook path reports across all inputs — so the wording carries real
information.

---

### 013. WONTFIX: manual dict counting in `_unique_titles`
*2026-05-29 · Rejected (won't change)*

**Context.** `_unique_titles` tracks collision suffixes with a manual dict;
`collections.Counter`/`defaultdict` could do the same.

**Decision.** Leave the manual counting as-is.

**Why.** Pure style preference; the current code is readable and the churn
isn't worth it.

---

### 014. Standardize release tags on the `v` prefix
*2026-05-29 · Accepted*

**Context.** Git tags are inconsistently named: `0.1.0`, `0.2.0`, `0.3.0`
have no prefix, while `v0.4.0` and `v0.4.1` do. The `v` prefix first appeared
at 0.4.0.

**Decision.** Use the `v` prefix (`vMAJOR.MINOR.PATCH`) for all future release
tags. Leave the existing unprefixed `0.x` tags as they are.

**Why.** One convention is easier to match in tooling and sorts predictably;
prefixed tags are the more common ecosystem convention. Existing tags are
published history, so we don't rewrite them — we just stop adding to the
inconsistency.

---

### 015. Clamp sheet titles to 31 characters in `_unique_titles`
*2026-05-29 · Accepted*

**Context.** XLSX caps worksheet titles at 31 characters. `_unique_titles`
never enforced this, so long stems (or long parent-qualified titles) produced
sheet names that triggered openpyxl's "Title is more than 31 characters"
warning and could be unreadable in some applications.

**Decision.** Clamp every generated title to `XLSX_TITLE_LIMIT` (31) inside
`_unique_titles`, and dedup on the *clamped* candidate, trimming the base so any
`_2`/`_3` suffix still fits within the limit.

**Why.** Titles are assigned in `build_databook` before the output format is
known, so clamping there — rather than branching in the XLSX save path — keeps
with the "no static capability matrix" principle (008): one short cap is safe
for every Databook format, no per-format conditional. The switch from the
per-base `seen` dict to a `used` set with a fit-and-retry loop is a correctness
requirement, not the style churn rejected in 013: truncation can make two
distinct long stems collide at char 31, which the old full-base dict would have
emitted as duplicate sheet names.

---

### 016. `--sheet` rejects single-sheet inputs; `--list-sheets` reports observed sheets, not capability
*2026-05-31 · Accepted*

**Context.** The TODO 3 draft had `--sheet 0 users.csv` succeed on a
single-sheet input, and the shipped `--list-sheets` (0.5.0) printed a
synthesized `[0] {stem}` line for such inputs. Both imply a sheet index and
identity for inputs that have neither.

**Decision.**
- `--sheet` is **rejected** on any input that resolves to a single sheet, with
  an *observational* message ("input resolved to a single sheet; `--sheet`
  applies to multi-sheet inputs") — never a capability claim about the format.
- `--list-sheets` reports only what was observed: multi-sheet input →
  `[idx] title  N rows x M cols`; single-sheet input → the real title when the
  loaded object carries one (a size-1 `Databook`, e.g. a one-sheet XLSX), no
  title for a fallback `Dataset` (CSV / records-shaped JSON), and **no
  `[index]`** in either single-sheet case.
- Integer-looking `--sheet` tokens are **always** 0-based indices; out of range
  errors rather than falling back to a title match. Non-integer tokens match
  titles (exact, then case-insensitive).

**Why.** We can't say a file "cannot contain multiple sheets" without a static
`{format: supports_databook}` table, which 008 bans: `load_databook_file`
returning `None` conflates a genuinely single-sheet format (CSV) with a
Databook-capable format holding single-Dataset shape (records JSON). The
observational wording states only the fact we have — this input is one sheet —
and stays 008-safe. A fabricated `[0] {stem}` index also advertises `--sheet 0`,
which we then reject, so dropping the synthesized index removes a false
affordance. `sheet.title` truthiness distinguishes the two single-sheet origins
(real Databook title vs `None` on a fallback Dataset) without re-checking the
loaded type or consulting a format table. Always-index keeps token resolution
predictable; a numeric *title* is a vanishing edge not worth the typo-masking
cost of an index-then-title fallback. This reverses the TODO 3 draft and changes
`--list-sheets` output shipped in 0.5.0. (Commit `a8c44c1`.)

---

### 017. Selection follows structure and is orthogonal to output; supersedes 016's rejection rule
*2026-07-04 · Accepted*

**Context.** A design review of the multi-sheet roadmap (2026-07-04) found two
flaws in the 016-era spec. First, 016's blanket rejection of `--sheet` on any
single-sheet input recreated the false-affordance problem it was written to
fix, mirrored: `--list-sheets` prints the real title of a one-sheet XLSX, but
passing that title to `--sheet` was rejected; TODO 4's "csv can't take a
Databook — pass `--sheet`" advice and 016's rejection pointed at each other in
a circle on one-sheet workbooks; and scripts like `--sheet Data monthly.xlsx`
broke precisely on the degenerate month where the workbook contains only
`Data`. Second, the draft entangled selection *arity* with output *mode*:
`--sheet A,B` refused to print to the terminal (error pointing at
`--all-sheets`, which shows all sheets, not the requested two) while
`--all-sheets` printed happily, and the analogous split existed for `-t`
stdout export.

**Decision.**
- **Selectability = observed structure.** An input that loaded as a `Databook`
  — *any* size, including 1 — has real sheets with real indices and titles;
  `--sheet` resolves against them normally. Only a fallback `Dataset`
  (CSV, records-shaped JSON) is rejected, with the observational message
  "input has no sheet structure". An empty workbook errors
  "workbook has no sheets".
- **`--list-sheets` output matches.** Every Databook, size-1 included, prints
  uniform `[idx] title  N rows x M cols` lines (restoring the index 016
  dropped — it is a true affordance now). A fallback Dataset prints one bare
  `N rows x M cols` line: no index, no title, nothing to select. Rule of
  thumb: whatever `--list-sheets` shows is exactly what `--sheet` accepts.
- **Selection is orthogonal to output.** `--sheet` picks a set of sheets and
  never changes which output modes are legal. One selected sheet takes the
  single-Dataset path; N sheets behave as a Databook of N sheets everywhere a
  Databook works — heading-separated terminal print, `-o` save, `-t` stdout
  export via the attempt-and-catch pattern (008). `--all-sheets` is sugar for
  "select everything" sharing the same code path. Because `--all-sheets`
  names no specific structure, it never fails on sheet-count grounds: on a
  structureless input it is the identity modifier (plain single render).
- **Token grammar hardening.** A `--sheet` argument is comma-split only when
  every comma-piece is an integer; otherwise the whole argument is one
  literal title token (protects titles like "Revenue, EMEA"). A `name:`
  prefix forces title interpretation (escape hatch for numeric titles like
  `2024`; the out-of-range index error mentions it when a matching title
  exists; a literal title starting with `name:` needs the prefix doubled).
  Ambiguous title matches — duplicate exact titles (legal in JSON/YAML
  books) or multiple case-insensitive hits — error listing the candidate
  indices rather than picking one. Title matching skips empty titles; index
  selection reaches everything.
- **Multi-input mode stays blunt.** `--sheet`/`--all-sheets` with 2+ inputs
  is an error ("not supported with multiple inputs"); expansion takes every
  sheet of every input. Per-input selection is deferred to the reserved
  `book.xlsx::Sheet1` syntax.

**Why.** Uniform interfaces are the robust choice (`head -1` works on
one-line files; `jq '.[0]'` works on singleton arrays): a request that is
unambiguous and satisfiable should not fail because the input is
degenerate-but-valid. Tying selectability to *observed structure* keeps
everything 016 actually cared about — no fabricated identities, no capability
claims, fully 008-safe (structure is discovered by the load attempt, not a
table) — while killing the list-shows-it-but-rejects-it inconsistency and the
error circle. Orthogonality is what makes the surface memorable: the `head`
precedent (one file bare, several files get `==>` headers) shows arity
changing *presentation*, never *legality*. This supersedes 016's rejection
clause and its single-sheet `--list-sheets` format; 016's other clauses stand
unchanged (0-based, integer tokens are always indices, exact-then-case-
insensitive title match, observational error wording). (Recorded with the
2026-07-04 TODO respec.)

---

### 018. Flag surface: `-l` moves to `--list-sheets`; `--list` becomes `--list-formats`; pandoc's `--from`/`--to`; `-s`
*2026-07-04 · Accepted*

**Context.** `-l/--list` was assigned to listing *formats* before multi-sheet
support existed. Listing formats is a rare, one-time discovery operation;
listing a workbook's *sheets* is the everyday one. tublub is zerover and
effectively single-user, so a coherent breaking rename is cheap now and
expensive later. The long-option pair `--in-format`/`--format` also undercuts
the `-f`/`-t` from/to mnemonic (bare `--format` surprisingly means *output*).

**Decision.**
- `-l` is reassigned to `--list-sheets`. `--list` is renamed to
  `--list-formats` (long-only). **No `--list` alias is kept**: with both new
  long flags defined, argparse's default prefix matching turns `--list` into
  an "ambiguous option: could match --list-formats, --list-sheets" error —
  a self-explaining migration message (so keep `allow_abbrev` on).
- Replace the long forms outright: `-f/--from` and `-t/--to` (pandoc's exact
  vocabulary — tublub is pandoc for tables). `--in-format` and `--format` are
  removed, not kept as aliases: one canonical long name per flag.
- Give `--sheet` the short `-s` (same frequency logic; `-s` is unused).
- Append the dynamic format list to `--help`'s epilog; `--list-formats`
  remains for scripting.

**Why.** Short flags should go to daily operations, and `-l` meaning "list
what's inside the file I gave you" matches `unzip -l` / `tar -t` / `7z l`
precedent, whereas `-l` for "list supported formats" has none. The transition
fails loud, never silent: bare `tublub -l` now errors "requires an input
file" (it used to print formats), `--list` hits the ambiguity error,
`-l FILE` was already an error under the old scheme, and
`--in-format`/`--format` become unrecognized-argument errors (neither is a
prefix of any remaining option) — so no previously working invocation
silently changes meaning. The short flags `-f`/`-t`, the daily-use
spellings, are untouched. Breaking; CHANGELOG entries land with the
implementation. (Recorded with the 2026-07-04 TODO respec.)

---

### 019. User-facing text never names Tablib internals
*2026-07-04 · Accepted*

**Context.** Tablib's internal type names leaked into user-facing strings:
the 0.5.0 save error said "does not support multi-sheet (Databook) output",
the `-o` help text and a `parser.error` said "Databook", and the README and
the respec'd TODO quoted "Databook" in message specs and in the three rules
destined for the README.

**Decision.** User-facing strings — errors, warnings, hints, `--help` text,
README prose — use plain vocabulary: "sheet(s)", "multi-sheet",
"sheet structure". They never name Tablib's internal types (`Dataset`,
`Databook`). The internal names stay where they belong: code, docstrings,
dev docs (`design.md`, this log, `TODO.md` internals).

**Why.** tublub's users convert files; Tablib is an implementation detail
they should never need to know about. "Multi-sheet" says exactly what
"Databook" means without requiring a trip to Tablib's docs. Applied
retroactively to the shipped 0.5.0 message and help text (CHANGELOG
`[0.6.0]`).

---

### 020. Injectable IO edges via optional keyword params, not a console object
*2026-07-04 · Accepted*

**Context.** Tests reached the CLI's IO edges only by monkeypatching process
globals: `sys.argv` for every `cli()` integration test, `sys.stdin.isatty`
for the implicit-stdin inference, `sys.stdin` itself (wrapped BytesIO) for
the stdin loaders, and hand-built fake `sys.stdout` objects for the export
handle. The multi-sheet roadmap multiplies exactly these paths (TODO 5 adds
a stderr TTY gate, TODO 7 routes three flags through stdin).

**Decision.** Every function that touches a `sys` stream or TTY state takes
an optional keyword-only parameter defaulting to `None`, resolved to the
real `sys` object *inside the body at call time*: `cli(argv)`,
`parse_command_line(argv, stdin_isatty=...)` (threaded to
`_should_use_implicit_stdin`, which probes the real stdin only after the
cheap checks so file-input invocations never touch it),
`stdin: IO[bytes]` on `_read_and_detect_stdin` and the three stdin loaders,
and `stdout: TextIO` on `_default_export_handle`. Tests inject argv lists,
booleans, and `BytesIO`/`TextIOWrapper` objects; no `monkeypatch.setattr(sys,
...)` remains. Did *not* introduce a `Console`/IO-context wrapper object.

**Why.** Injection keeps helpers reusable outside the CLI (003) — the stdin
loaders now accept any binary stream — and makes tests state exactly which
edge they exercise instead of mutating global state. A wrapper object was
rejected for the same reason as `InputSpec` in 009: more machinery than the
problem warrants. Defaults are `None`-resolved in the body, never in the
signature, because a `sys.stdout` default is captured at definition time —
the exact bug fixed in 0.4.0. New IO edges (TODO 5's stderr TTY gate,
TODO 7's stdin routing) must follow this pattern. Internal refactor, no
CHANGELOG entry.

---

### 021. Default conversion of a multi-sheet input goes whole-book; warn-fallback to first sheet
*2026-08-04 · Accepted*

**Context.** TODO 5's spec had default conversion (`-o`/`-t`, no selection
flags) of a multi-sheet input convert only the first sheet, with an
unconditional data-loss warning. The TODO 4 plan review (2026-08-04) found
this inconsistent with TODO 6's default: multi-input mode expands *every*
sheet of every input into the output, so
`tublub -o out.xlsx book.xlsx extra.csv` includes all of book.xlsx's sheets
while `tublub -o out.xlsx book.xlsx` would keep only the first — dropping
the second input from the command silently shrinks how the first is read.

**Decision.**
- Default conversion mirrors `--all-sheets`: an input observed to have
  sheet structure with 2+ sheets attempts a whole-book save/export; a
  size-1 workbook or structureless input behaves exactly as today (per
  017, one sheet takes the single-sheet path). Capability is discovered by
  attempting the export and catching failure (008), never from a table.
- When the target format cannot hold multiple sheets, default mode falls
  back to the first sheet with an **unconditional** stderr data-loss
  warning. The warning suggests `-s` only — never `--all-sheets`, which
  errors in that same situation.
- Explicit flags stay strict: `--all-sheets` and multi-sheet `--sheet`
  selections error where the default falls back. Asking for all sheets by
  name is a demand; the default is best-effort.
- Terminal print default is unchanged: first sheet plus the TTY-gated
  advice line (a 30-sheet dump to a terminal is noise, unlike a file).
- `--all-sheets` stays long-only (no `-a` short flag): the default absorbs
  its main daily use, whole-workbook conversion.

**Why.** Converters convert the whole document by default (pandoc does not
translate only chapter one); a converter that drops data by default
surprises exactly the users who least expect it. The uniformity argument
from 017 applies to arity here too: adding or removing a second input must
not change how the first is read. Whole-book-by-default also makes the
data-loss warning rare and meaningful — it fires only when the target
genuinely cannot hold the sheets. Accepted cost: output shape now depends
on sheet count (records-JSON for one sheet, book-JSON for several), but
`--all-sheets` already has that property under 017's one-sheet rule, and
scripts needing a stable shape pin `-s 0`. Implementation lands with the
TODO 5 increment, reusing TODO 4's `_render_databook`/`export_databook`;
the fallback needs a distinct failure signal (e.g. a `TublubError`
subclass) so it never swallows unrelated errors. This supersedes the
conversion-warning clause of the 2026-07-04 TODO 5 spec; the advice-line
clause stands. (Recorded at the TODO 4 plan review.)

---

### 022. Terminal print is the `cli` export; `__str__` is the fallback
*2026-08-04 · Accepted*

**Context.** `tublub data.csv` and `tublub -t cli data.csv` rendered
differently: the print path used tablib's hand-rolled `Dataset.__str__`
(pipe-joined columns, dashed header rule) while `-t cli` used tablib's cli
format (a Tabulate wrapper). TODO 4's `_format_dataset_as_table` routed
through the cli export *only* when `--tablefmt` was given, so the flag
switched renderer rather than style — surprising, since nothing in the CLI
suggests two table engines exist.

**Decision.**
- The default terminal print path renders through the same `cli` export as
  `-t cli`, for single sheets and for each sheet of a multi-sheet print.
  The two invocations are byte-identical.
- **No tublub-chosen default style.** We pass no `tablefmt` of our own, so
  tablib's `CLIFormat.DEFAULT_FMT` (Tabulate's `plain`) applies and
  `--tablefmt` is a pure style knob. Choosing our own default would mean
  owning a style opinion, and re-deciding it whenever the upstream default
  moves.
- **`str(dataset)` stays as a fallback**, used when `"cli" not in
  get_formats()`. Tablib registers the cli format only when `tabulate` is
  importable, so the registry lookup is runtime-observed capability, not a
  static table (008-safe). The fallback covers the default print path only;
  an explicit `-t cli` still fails loud in `_check_known_format`, because a
  format the user named by hand should not silently become another one.
- Text exports to stdout are newline-terminated (`export_dataset` /
  `export_databook`, only when the handle was defaulted). Without this,
  `-t cli` could never equal a `print()`-based path, and every text export
  left the shell prompt mid-line. Explicitly passed handles — every `-o`
  save — are written verbatim, so file bytes do not change.

**Why.** "The table I see by default is the table `--tablefmt` restyles" is
what users assume, and one renderer means one thing to document, test, and
reason about. Deferring the style to tablib/tabulate keeps tublub a thin
wrapper (000): we express *which* renderer, not *how* it should look. The
fallback costs three lines and keeps a `tablib` install without the `cli`
extra usable for its most basic operation instead of tracebacking.

Defaulting happens at **render time, not parse time**: we considered making
`args.out_format` default to `"cli"` when neither `-o` nor `-t` is given,
which would unify the paths even more aggressively. Rejected — bare print
and `-t cli` must stay *distinguishable internally* even though they render
alike: TODO 5's advice-vs-data-loss split (021) branches on "is this a
conversion or a terminal print", and `--list-sheets` validation rejects a
combined `-t`, which a phantom default would trip. The user-visible result
is the same either way, so we take the version that keeps the explicitness
signal. Breaking only in appearance; CHANGELOG `[0.6.0]`.

---

### 023. Default mode reads stdin like a file; empty-workbook wording stays source-named
*2026-08-04 · Accepted*

**Context.** Implementing 021 raised three questions 021 did not answer.
TODO 5's task text names only `try_load_file`, so a literal reading would
leave the stdin branch of `_run_single` on `load_dataset_stdin` —
`cat book.xlsx | tublub -f xlsx -o out.ods` would keep dropping sheets that
`tublub book.xlsx -o out.ods` now preserves. Loading through `try_load_*`
also routes a size-0 Databook (an empty JSON/YAML workbook) into the default
path for the first time, where 017's selection message "workbook has no
sheets" and 012's source-naming "No data was loaded from {source}" compete.
And `Databook.export("cli")` turns out to be unsupported, so `-t cli` is a
failing conversion rather than a view.

**Decision.**
- **Default mode loads stdin through `try_load_stdin`**, not
  `load_dataset_stdin`. `cli()` gains an injectable `stdin` edge (020) so the
  path is testable. TODO 7 keeps the rest of its scope: lifting the
  `--list-sheets`/`--sheet`/`--all-sheets` stdin rejections.
- **An empty workbook in default mode keeps "No data was loaded from
  {source}"**; "workbook has no sheets" stays the selection path's message.
  Extends 012's distinctness rule to the Databook-in-default-mode case.
- **`-t cli` is a conversion, not a view.** It gets the unconditional
  data-loss warning; only the bare terminal print gets the TTY-gated advice.
  Stdout stays byte-identical between the two (022 holds); only stderr
  differs.

**Why.** 021's own argument — "adding or removing a second input must not
change how the first is read" — applies unchanged to moving an input from
argv into a pipe; an input-source-dependent data-loss rule would be the same
surprise in a different costume. The empty-workbook wording follows 012: the
default path names the file it read, which is the only information the user
lacks, whereas someone who typed `--all-sheets` already knows the source and
needs to know the *structure* is empty. Treating `-t cli` as a conversion
keeps one rule — "did the user name an output format or file?" — rather than
a special case for the one format that happens to look like the default
view. Refines 021 and 012; supersedes nothing. (Recorded at the TODO 5 plan
review.)

---

### 024. Multi-input expansion keeps original sheet titles; only clashes are qualified
*2026-08-04 · Accepted*

**Context.** TODO 6's task text specified that in multi-input mode every
sheet of a multi-sheet input be retitled `f"{path.stem}__{sheet.title}"`
unconditionally, with `_unique_titles` widened so 015's clamp-and-suffix
machinery applied on top. Implementing it exposed the cost: every other
shipped multi-sheet path — `_convert_whole_book` (021), `--all-sheets` and
`-s` subsets (017) — writes sheet titles through verbatim, so
`tublub -o out.xlsx book.xlsx` preserved `Users` while
`tublub -o out.xlsx book.xlsx extra.csv` renamed it to `book__Users`. Adding
an unrelated second input would rename the first input's sheets.

**Decision.**
- **Expansion keeps titles verbatim; qualification is clash-only.** Each
  contributed sheet carries a `(preferred, qualified)` pair. A preferred
  title that occurs once is used as-is; one that occurs two or more times
  (exact match) falls back to its qualified form. Both clash parties
  qualify — the winner is not decided by input order.
- **The qualified form names the sheet's container:** a workbook sheet takes
  its file stem (`book__Users`), a whole-file sheet takes its parent
  directory (`hr_people`, the shipped 015 rule). A path with no parent name
  qualifies to its own stem, which then falls to the numeric suffix.
- **015's tail is unchanged and applies to whichever form was chosen:**
  right-truncate the whole string to 31 characters, then `_2`/`_3` on
  residual collisions with the base trimmed to fit. No budget split between
  the stem and sheet-title halves of `stem__title`.
- **`_unique_titles` takes `list[tuple[str, str]]`**, not paths — the caller
  derives both forms, since only it knows whether a sheet came from a
  workbook or a whole file. The stderr note stays inside it, comparing final
  against preferred: under clash-only qualification every difference is
  genuine disambiguation, so no separate "naive title" bookkeeping is
  needed.
- **Untitled sheets are not special-cased.** An empty title is a preferred
  title like any other: unique on its own, qualified to `stem__` on clash.

**Why.** 021's rule — "adding or removing a second input must not change how
the first is read" — extends to how it is *named*; a scheme where sheet names
depend on argv length is the same surprise in a different costume.
Preservation is also what the format's own tools do: merging workbooks in a
spreadsheet application keeps sheet names and only disambiguates duplicates.
Accepted cost, and the reason unconditional prefixing was tempting: output
names now depend on cross-input contents, so introducing a new clash can
rename a previously stable sheet — but that is exactly the case where a
stable name is impossible anyway, and the note announces it. Rejected the
"scripts want a predictable `stem__title`" argument: a script that needs
fixed sheet names is better served by one `-s` invocation per sheet than by
tublub renaming everything on the chance of a collision. Supersedes TODO 6's
title-derivation wording; 015's clamp-and-suffix rules and the note stand
unchanged. (Recorded at the TODO 6 plan review.)

---

### 025. An existing output file is asked about at a terminal and refused everywhere else
*2026-08-06 · Accepted*

**Context.** Every write path overwrote its output file without asking, and the
two-positional `[INFILE [OUTFILE]]` form made that easy to trigger by accident:
`tublub -s 0 a.xlsx b.csv` meant as two inputs rewrote `b.csv`, because
multi-input mode needs `-o`. `ffmpeg` is the closest analogue — it prompts by
default and takes `-y`/`-n` to decide up front. The TODO sketch left two
questions open: what the default should do when no one can be asked, and what a
refusal should exit with.

**Decision.**
- **`-y/--yes` and `-n/--no-clobber`**, plain `store_true` in the output group,
  combined rejected by `parser.error` like the other flag combos. `-y`
  overwrites, `-n` refuses.
- **With neither flag, an existing output file is asked about only at a
  terminal:** the question goes to stderr because stdout may be the data
  stream, defaults to no, and accepts `y`/`yes` case-insensitively. End of
  input counts as no.
- **When stdin is not a terminal, the default refuses** rather than
  overwriting, with the same message `-n` gives.
- **Every refusal exits non-zero** — `-n`, the non-terminal default, and a
  declined question alike.
- **One check in `cli()`,** after the `--list-formats` short-circuit and before
  any dispatch, reading the single `args.outfile` that both `-o` and the
  positional form resolve to. Never in `save_dataset_file` /
  `save_databook_file`: those stay usable outside the CLI, and a library helper
  must not block on stdin (003).
- **The two new IO edges are injected, not patched** (020): `cli()` grew
  `prompt_input` for the answer and now threads `stdin_isatty` on to
  `parse_command_line` as well. The terminal test reads that flag rather than
  asking the answer stream, whose `isatty()` is false whenever a test supplies
  the answer from memory.
- **Neither flag means anything without an output file** — printing to stdout,
  or a path that does not exist yet, passes straight through — so both are
  harmless no-ops there rather than a rejected combination.

**Why.** Refusing on a non-terminal is the half that protects the case which
prompted this: the accidental overwrite was done by an agent, and an agent
harness is not a terminal, so a prompt-only guard would have protected nobody
who needed it. It costs scripts one `-y`, which is the same bargain `ffmpeg`
strikes, and it makes the flags rather than the terminal the load-bearing part
of the design. Non-zero on refusal follows from what a converter is: it wrote
nothing, so it did not do what it was asked, and exit 0 would hide a skipped
conversion from the script that asked for it — modern GNU `cp -n` reaches the
same conclusion after shipping the opposite. Supersedes the TODO sketch's
implied "scripts never block" default and settles both of its open questions.
Accepted as a breaking change: `-y` is a one-flag escape, and silently
destroying data is the worse default to keep.

---

### 026. A multi-sheet save renders its payload before opening the output file
*2026-08-06 · Accepted*

**Context.** `save_databook_file` opened the output for writing — which
truncates — and only then called `export_databook`, the attempt that discovers
whether the target format can hold several sheets (008). So a refused
conversion destroyed the file it declined to write:
`tublub -y --all-sheets -o victim.csv book.xlsx` printed "Format 'csv' does not
support multi-sheet output", exited 1, and left `victim.csv` at 0 bytes. The
025 guard runs earlier and is unaffected — `-y` authorises a *conversion*, not
a wipe. The 021 fallback path survived only by accident: `_convert_whole_book`
caught the error after the truncation and `save_dataset_file` reopened the same
path with the first sheet.

**Decision.**
- `save_databook_file` exports into an `io.BytesIO`/`io.StringIO` chosen from
  the format's `binary` flag, then opens the real file and writes the finished
  payload. Nothing touches the output path until the export has succeeded.
- `export_databook` stays the single error boundary and is reused unchanged;
  only the ordering moves. The 021 fallback now branches before the file has
  been opened at all, so it survives by design rather than by accident.
- **Not** a temporary file plus rename: that would change the identity of the
  output path (symlinks, hard links, ownership, permissions) on *every* save,
  not just the failing one.
- `save_dataset_file` keeps writing straight to the file. Its post-open
  failures are raw Tablib tracebacks on degenerate data (an empty sheet to dbf
  raises `IndexError`), not a designed rejection, so there is no error to move
  ahead of the open.

**Why.** Destroying data on the path that refuses to write it is the worst
failure a converter has: the user still has the input, but the *other* file is
gone, and nothing in the error says so. Buffering costs one extra copy of a
payload `book.export()` already materialises in full — Tablib has no streaming
export, so the payload exists in memory either way.

This supersedes the TODO sketch's mechanism, which proposed deciding the
format's book capability *before* opening anything, on the grounds that
capability is a per-format fact. It is not askable that way: an empty
`tablib.Databook().export(fmt)` raises `IndexError` for xls and xlsx (openpyxl
needs at least one visible sheet), not `UnsupportedFormat`, so a synthetic
probe cannot separate "cannot hold sheets" from "cannot hold *no* sheets". A
static table is what 008 exists to forbid. Attempting the real export and
buffering the result answers the same question with the data actually being
saved. The sketch's ban on temp-file-and-rename stands.

---

### 027. `try_load_file` reads and detects once, like the stdin path
*2026-08-06 · Accepted*

**Context.** `try_load_file` called `load_databook_file` and then, on the
Dataset fallback, `load_dataset_file` — and each resolved the input format
for itself, with `_resolve_input_format` re-reading the file for detection
and printing the extension/content mismatch warning unconditionally. A CSV
named `data.xls` (004's own example) warned twice and was read four times.
Pre-existing, but the 0.6.0 whole-book default (021, 023) moved it from the
rare selection paths onto the default path. The TODO entry named two clean
fixes, each changing when the warning fires: short-circuit
`_resolve_input_format` when `-f` is given, or read and detect once in
`try_load_file` and pass the payload down.

**Decision.** `try_load_file` reads the file's bytes once, resolves the
format once (`_resolve_input_format` accepts already-read bytes; the
read-and-detect `detect_format_from_file` wrapper is gone), and tries the
Databook interpretation with Dataset fallback on that same payload via
`_import_any`, a helper shared with `try_load_stdin`. The mismatch warning
now fires once per loaded input — still including under `-f`, as before.
The per-type helpers `load_databook_file` / `load_dataset_file` keep their
own resolution and per-format open path, like their stdin twins.

**Why.** This is the shape 011 already required of stdin ("try both
interpretations on one read"), so files and stdin now load identically;
that a file *can* be re-read was the only reason it ever took the lazier
shape. The `-f` short-circuit was rejected because it would silence 004's
reconfirmed warn-and-continue policy in exactly the wrong-extension case
that policy exists for, while still reading the payload more than once
without `-f`. Handing Tablib decoded bytes instead of a newline-configured
file handle is what every stdin load has always done, and csv — the only
format with an open rule (`newline=""`) — reads bytes-transparently; the
per-format open table (000) still governs writes and the per-type file
helpers.

---

### 028. A single input with no sheet structure is titled after its source, at load time
*2026-08-06 · Accepted*

**Context.** `tublub customers.csv out.xlsx` wrote a sheet named
`Tablib Dataset` — Tablib's placeholder when `Dataset.title` is `None`, which
only the ods/xls/xlsx exports substitute (the html export uses `Set {i}`, and no
single-Dataset export renders a title at all). Titles were assigned only in
`build_databook`, so `-o out.xlsx a.csv b.csv` named its sheets `a`/`b` while
`-o out.xlsx a.csv` named its one sheet `Tablib Dataset`: dropping the second
input changed how the *first* was named. The TODO sketch left one question open —
stdin has no stem, so keep the placeholder or name it `stdin`?

**Decision.**
- **A payload that loaded as a fallback `Dataset` — no observed sheet structure —
  is titled after its source**, clamped through `_fit_title`. A file takes its
  stem, matching the title `build_databook` would give it. Observed sheet titles
  are never touched.
- **Stdin is named `stdin`.** A pipe has no stem, but `stdin` is the source name
  the error messages already use, and it is what the multi-input rule would give
  a source called `stdin` anyway.
- **Titling happens at load, in `_import_any`**, the branch shared by
  `try_load_file` and `try_load_stdin`, rather than in the single-input
  save/export path the sketch named. One place titles and clamps; both callers
  must say what their source is called.
- **No disambiguation note.** A single sheet cannot collide with anything, so the
  stderr note stays `_unique_titles`' concern.

**Why.** This is 021's arity rule — adding or removing a second input must not
change how the first is read — applied to how it is *named*, which is exactly
what 024 established for the multi-input side. 019 supplies the second argument:
`Tablib Dataset` ships a Tablib internal *inside the user's file*, the same leak
019 removed from messages and help text, and it is the one place a user cannot
avoid reading it.

Load-time placement is what the sketch's own reasoning requires, not a
convenience. 017 makes `--all-sheets` the identity modifier on a structureless
input, so titling only in the single-input path would have left
`--all-sheets -o out.xlsx a.csv` writing `Tablib Dataset` where
`a.csv out.xlsx` wrote `a` — a new arity surprise in place of the one being
fixed. The same move 023 made for stdin loading: put the behaviour where every
path that should share it already passes. Placement is also observationally free:
no print or export path renders a Dataset's title except the three formats this
entry is about.

Not a breaking output change for records-shaped json/yaml or the single-sheet
text formats — none of them carries a sheet name. Supersedes the sketch's
save/export placement wording and settles its open stdin question.

---

### 029. The manual page is the user manual; the README is a landing page
*2026-08-07 · Accepted*

**Context.** `README.md` had grown to 139 lines, 83 of them a multi-sheet
manual — the three selection rules, the every-sheet conversion policy, the
single-sheet fallback, the strictness of `--all-sheets`, worked examples of
each. That is reference documentation living on a landing page, and it was
already stale: the first output example still showed Tablib's old
pipe-separated rendering rather than the table the `cli` default has printed
since 0.5.0. A second problem was reach — the reference was only readable on
GitHub, and a CLI tool is expected to answer `man tublub`.

**Decision.**
- **The manual page is the reference; the README is a landing page.** The
  multi-sheet manual moves to a new `docs/tublub.1.md`, written in Pandoc
  Markdown with YAML front matter. The README keeps the pitch, the example
  block, the `-o` and overwrite paragraphs, a short multi-sheet teaser, install
  instructions, and a pointer to the page.
- **Generated at build time, never committed.** `just build_man` runs pandoc
  into `data/share/man/man1/tublub.1`; everything under `data/` is gitignored
  except a `.gitkeep` holding the directory itself, because uv_build fails
  outright when a configured data dir is missing and `uv run` builds the
  project — without the placeholder, a fresh clone can not even run the tests.
  `wheel-exclude` keeps that placeholder out of installed environments, while
  leaving it in the sdist, which is what keeps the directory present for the
  wheel build. `just build` chains the man page before `uv build`, and the
  publish workflow does the same (apt pandoc, pinned
  `extractions/setup-just`) since uv_build has no build hooks that could run
  pandoc from inside `uv build`.
- **`footer` and `date` are injected at build time** with `pandoc -M`, not
  written into the front matter, so no release step has to bump them and
  `RELEASING.md` is unchanged.
- **Shipped via the wheel's data directory**, `[tool.uv.build-backend.data]
  data = "data"`, which installs to `<prefix>/share/man/man1/tublub.1`.
- **Built with `-f markdown-smart`.** Pandoc's `smart` extension renders
  `--verbose` as an en dash plus `verbose`; disabling it is what keeps long
  options readable in roff.
- **A test guards the OPTIONS list.** `test_man_page_documents_every_long_option`
  regexes the long flags out of `format_help()` and asserts each appears in
  `docs/tublub.1.md`.

**Why.** The multi-sheet roadmap declined a README flag table because a second
list of flags drifts from `--help`, and that reasoning survives here: the
manual page's OPTIONS section *is* that second list, so it only earns its place
with a drift guard, which is why the sync test is part of this decision rather
than an extra. One reference is also the point of moving the manual at all —
a landing page that documents behaviour competes with the page that is supposed
to.

Generating rather than committing follows the same rule the project already
applies to `uv.lock` pins and version strings: one source of truth, no
hand-maintained derivative. Committing the roff would mean reviewing generated
diffs and would let the two files disagree.

Both wheel-data choices were verified rather than assumed. uv_build's data
directory was probed first, before any documentation was written, since a
closed uv issue reports data directories silently missing from
distributions: the `.1` appears in both the sdist and the wheel (uv_build does
not skip the gitignored directory), and installing the wheel into a scratch
venv puts it at `<venv>/share/man/man1/tublub.1` — the same place odfpy, an
existing dependency, ships its own pages. Switching to hatchling's
`shared-data` was the approved fallback and turned out not to be needed. The
manpath exposure is pipx's: 1.5 and later symlink a package's
`share/man/man[1-9]/*` into `PIPX_MAN_DIR`. `uv tool install` does not do this
yet (astral-sh/uv#4731), so the README says so rather than implying `man
tublub` works everywhere.

The Pandoc-Markdown-with-front-matter shape, the `build_man` recipe name, and
the apt-pandoc workflow step are all taken from the sibling `pylendar`
project, where this pipeline is already in production. The two divergences from
it are deliberate: build-time `footer`/`date` injection instead of hardcoded
front matter, and `-f markdown-smart` — pylendar's page currently renders its
own `--init` and `--version` with an en dash for want of it.

### 030. `--sheet` index ranges: cut's increasing shapes only, expanded at resolution
*2026-08-07 · Accepted*

**Context.** The TODO listed index ranges (`--sheet 0-4`) as a fit for 017's
integers-only comma rule. cut(1) is the natural grammar to borrow, but it has
three shapes (`N-M`, `N-`, `-M`) and silently tolerates out-of-range fields,
while tublub already promises that integer-looking tokens are always indices
(016) and that an occurrence comma-splits only when every piece is a selector
(017).

**Decision.**

- Two shapes: closed `N-M` (0-based, inclusive both ends) and open-ended `N-`
  (through the last sheet). Endpoints are bare decimal digits; a sign, inner
  whitespace, or a second dash makes the token a title.
- cut's `-M` prefix shape is deliberately omitted: `-s -1` keeps erroring
  "sheet index -1 out of range", guarding users who expect Python-style
  negative indexing; `0-M` spells the prefix range explicitly.
- A decreasing range (`4-2`) is a parse-time error ("invalid decreasing sheet
  range 4-2"), like cut's "invalid decreasing range" — a static defect that
  needs no input to diagnose.
- Ranges join 017's comma grammar: an occurrence splits when every piece is an
  integer *or a range*, else it stays one literal title token. Range-shaped
  tokens are always ranges, never title matches, extending 016's always-index
  rule; `name:` remains the escape hatch for a sheet titled like a range.
  017's grammar clause is extended, not otherwise changed. A mixed attempt
  like `-s 2-4,Users` therefore stays a title miss; its hint is reworded to
  "repeat --sheet to combine names with indices or ranges", and stays generic
  because echoing a concrete split would mislead for a genuine
  comma-containing title.
- Expansion happens at resolution time — an open end needs the sheet count —
  and an endpoint past the last sheet errors ("sheet range 0-4 out of range
  (0-2)", with the `name:` hint when a title matches the token) rather than
  clamping. Expanded indices feed the same order-preserving first-occurrence
  dedup as plain indices; a range that reduces to one sheet takes the plain
  single-sheet render path.
- The no-such-title error lists at most ten titles and then says "and N more,
  run --list-sheets to see them all"; when no sheet carries a title it says
  "this input's sheets have no titles, select by index" instead of trailing a
  bare colon.
- A hint about how to fix the command — the `name:` escape hatch, the repeat
  suggestion — goes on its own line rather than after another semicolon. The
  elision marker stays attached to the listing it truncates, since it says
  what is missing rather than what to type.

**Why.** Ranges must not weaken the two guarantees that make the selector
grammar predictable: a numeric-looking token is never quietly a title, and a
selector naming sheets the input does not have is a mistake, not a shorthand.
cut's silent tolerance suits field streams, not named selections, so an
out-of-range range errors exactly as an out-of-range index does (016).
Dropping `-M` costs nothing (`0-M` exists) and keeps `-1` an error surface for
the most likely misreading of the syntax. Expanding through the existing dedup
keeps ranges a pure spelling shortcut: `-s 0-2` and `-s 0,1,2` are the same
request everywhere downstream.

Capping the title listing rather than replacing it with a pointer keeps the
common case cheap: most workbooks have a handful of sheets, where the list is
itself the answer and a second command would be pure overhead. Past the cap it
stops being something you can fix a typo from at a glance — a plausible
24-sheet quarterly workbook produced a 713-character single-line error — and
017's rule of thumb already makes `--list-sheets` the canonical listing, with
indices and sizes the error cannot show. Breaking the fix onto its own line
follows from the same measurement: a hint appended to a listing that wraps
across several terminal lines is a hint nobody finds.

---

### 031. Every save renders its payload before opening the output file
*2026-08-08 · Accepted*

**Context.** 026 buffered the multi-sheet save but kept its last bullet:
`save_dataset_file` writes straight to the file, on the premise that its
post-open failures are "raw Tablib tracebacks on degenerate data, not a
designed rejection, so there is no error to move ahead of the open". The
premise was wrong about the data: exports fail on inputs that are merely
degenerate *for the target*, not degenerate outright. `tublub -H -t dbf -y -o
out.dbf users.csv` (dbf needs a header row) raised `TypeError` after the
truncation and left `out.dbf` at 0 bytes; a CSV cell holding a control byte
did the same to an existing `.xlsx` via openpyxl's `IllegalCharacterError`.
Real inputs hit both.

**Decision.**
- `save_dataset_file` buffers exactly as `save_databook_file` does: export
  into an `io.BytesIO`/`io.StringIO` chosen from the format's `binary` flag,
  then open the real file and write the finished payload. This supersedes
  026's `save_dataset_file` bullet; everything else in 026 stands, including
  the ban on temp-file-and-rename.
- The failures become a designed rejection: `export_dataset` and
  `export_databook` wrap whatever the export raised in a `TublubError`
  ("Could not export to FMT: ...") via `_export_error`. The catch is broad by
  design — a format's writer signals "this data will not fit" with whatever
  its backend happened to raise, so the exception type carries nothing worth
  branching on. `export_databook`'s `UnsupportedFormat` →
  `MultiSheetUnsupportedError` clause stays first and untouched.

**Why.** 026's own rationale applied all along: destroying data on the path
that refuses to write it is the worst failure a converter has. The bullet
survived because the failing exports were assumed unreachable from sane
input, and `-H` alone disproves that. Wrapping the error is part of the same
fix — the traceback was the symptom that made the truncation look like a
crash instead of a policy.

---

### 032. A `TypeError` from a workbook load is probed, not trusted
*2026-08-08 · Accepted*

**Context.** 008 catches `UnsupportedFormat`/`KeyError`/`TypeError` around
`Databook().load()` and treats all three as "not a workbook — fall back to a
single sheet". But `TypeError` has a second cause: the workbook readers for
xlsx and xls accept no `skip_lines`, so `--skip-lines 1` on a genuine
multi-sheet workbook raised `TypeError` from the *kwarg*, fell back, and
silently read only the first sheet — `tublub -l --skip-lines 1 book.xlsx`
listed one anonymous sheet where the workbook has four, and `-s 2` claimed
the input had no sheet structure.

**Decision.** The shared `_load_book` helper (now used by `_import_any`,
`load_databook_file` and `load_databook_stdin`) separates the two causes by
retrying: on `TypeError` with load options present, attempt the plain load
with no options. If the plain load yields two or more sheets, the input
really is multi-sheet and the options are what failed — raise a `TublubError`
naming the flags ("--skip-lines is not supported for multi-sheet input") with
the workaround on its own line. If it yields one sheet or fails, fall back as
before: the single-sheet fallback loses nothing and *applies* the options,
which is why `--skip-lines` on a one-sheet xlsx keeps working. No message
sniffing on the `TypeError`, and still no static capability table — the probe
is itself an attempt, in 008's spirit.

**Why.** The fallback exists to answer a shape question, and a kwarg
rejection is not a shape answer. Conflating them made a data-dropping path
out of an option that works fine on every single-sheet input; erroring only
when the retry proves sheets would be lost keeps the flag maximally useful
while making the loss impossible to hit silently. The retry costs one extra
parse only on the path that previously ended in silent loss.

---

### 033. OS errors are converted to clean messages at the CLI boundary
*2026-08-29 · Accepted*

**Context.** 003 routes user-facing problems through `TublubError`, which
only the CLI layer converts to `sys.exit(msg)`. But the operating system
reports its own class of user-facing problems — an unreadable input file, an
output path whose directory does not exist, a directory where a file was
expected — and those escaped as raw `OSError` tracebacks (`IsADirectoryError`,
`FileNotFoundError`, `PermissionError`), the same symptom the 0.8.1 release
fixed for non-UTF-8 input. The parse-time `is_file()` check cannot close this:
readability is only known at open time, and output paths are not checked at
all.

**Decision.** `cli()` wraps its mode dispatch in one `except OSError` and
exits with `_os_error_message(exc)` — "Cannot open '<path>': <strerror>" when
the error names a file, a generic input/output line otherwise. Library
helpers do not catch or wrap `OSError`; a Python caller keeps the real
exception, exactly as 003 keeps `TublubError` catchable.

**Why.** The OS is hit in many places (open, read, the final write), so
converting at each call site would sprinkle the same handler everywhere and
inevitably miss one; the boundary already exists and catches everything below
it, future call sites included. Reusing the OS's own `strerror` instead of
composing per-case messages follows the same instinct as 008's "ask, don't
tabulate": the kernel already names the failure better than a hand-rolled
message table would.
