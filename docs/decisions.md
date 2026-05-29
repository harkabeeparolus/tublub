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
