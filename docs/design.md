# tublub — design

The durable "how it's built and why" for tublub. Read this before changing
format detection, error handling, or the Dataset/Databook split. For the
record of specific calls (and their dates/rationale), see
[`decisions.md`](decisions.md). For the multi-sheet feature roadmap, see
[`TODO.md`](TODO.md). This doc is living — revise it as the design
evolves; `decisions.md` is append-only.

## What tublub is

A thin CLI wrapper over [Tablib](https://tablib.readthedocs.io) that converts
and views tabular data between formats (CSV, TSV, JSON, YAML, XLSX, XLS, ODS,
DBF, and Tablib's export-only formats).

**Why it exists.** Tablib knows how to *parse and serialize* each format, but
not how to *open the file on disk* for it — binary vs text mode, newline
handling — which historically was documented only in Tablib's web docs, per
format. tublub's founding contribution is encoding that per-format file-open
knowledge in code (the `FORMATS` table below), so callers never have to look
it up. See [`decisions.md` 000](decisions.md).

**Design philosophy: don't reimplement Tablib.** tublub adds a command-line
surface, format detection, and ergonomics; Tablib owns the actual parsing,
serialization, and the set of supported formats. Wherever a choice is between
"teach tublub about formats" and "ask Tablib and react", we ask Tablib (see
*No static capability matrix* below).

This extends to dependencies: tublub pulls in only Tablib's **file-format**
extras (`tablib[cli,html,ods,xls,xlsx,yaml]`), never the ones aimed at Python
developers manipulating data in code (e.g. Pandas). When Tablib's extras
change, the test for adopting a new one is simply "is it a file format?" (see
[`decisions.md` 001](decisions.md)).

## Module layout

Single module: `src/tublub/main.py`. Entry point `tublub.main:cli`. The flow
is layered:

1. **Parse + validate** — `parse_command_line` builds the argparse parser,
   reconciles positionals, resolves stdin, validates, and collects
   format-specific kwargs (`_collect_extra_args`).
2. **Dispatch** — `cli()` is a flat switch over modes, one `_run_*` per mode
   (see *Dispatch model*).
3. **Load / save helpers** — `load_*`/`save_*`/`try_load_*`, all built on the
   `FORMATS` table.
4. **Tablib** — does the real work.

## Core abstractions

### The `FORMATS` table
`FORMATS: dict[str, FormatConfig]` is the single source of per-format
behavior: `binary?`, allowed load/save kwargs, and open kwargs (only CSV sets
a non-default `newline`). **Adding or tweaking a format means editing one
entry**, not sprinkling conditionals through the loaders. `filter_args` and
`_open_for_format` both read from it so call sites never branch on format
themselves.

There is deliberately **no `databook: bool` capability flag** — see below.

### The `TublubError` boundary
Library helpers raise `TublubError` for user-facing problems; only the
`_run_*` entry points (called by `cli()`) catch it and convert to
`sys.exit(msg)`. This keeps every helper reusable outside the CLI. For type
narrowing, prefer an explicit `if x is None: raise TublubError(...)` or a
helper with an already-narrow return type over `assert`/`cast` (S101 forbids
`assert` in `src/`).

User-facing text (error messages, warnings, hints, `--help`, README) speaks
the user's vocabulary — "sheet(s)", "multi-sheet" — never Tablib's internal
type names (`Dataset`, `Databook`); those belong in code and dev docs only
(see [`decisions.md` 019](decisions.md)).

### Dataset vs Databook
A single sheet is a `tablib.Dataset`; a multi-sheet workbook is a
`tablib.Databook`. Most load/save operations have both flavours. The
`try_load_file` / `try_load_stdin` helpers encapsulate the **"try Databook,
fall back to Dataset"** handshake so call sites don't reimplement it (stdin
in particular can only be read once, so the stdin variant tries both
interpretations on the same bytes).

### Input state
`args.infiles: list[Path]` and `args.stdin: bool` are the **only** input-state
truth. There is no separate `args.infile` or `InputSpec` wrapper. Stdin is
inferred in `parse_command_line` (explicit `-`, or no inputs piped into a
non-TTY — see `_should_use_implicit_stdin`).

## Key design principles

### No static Tablib capability matrix
Discover what a format can do by **attempting the operation and catching the
failure**, never by consulting a hard-coded table. `save_databook_file`
attempts `book.export(fmt)` and catches `tablib.UnsupportedFormat`;
`load_databook_*` attempts `Databook().load(...)` and catches
`(UnsupportedFormat, KeyError, TypeError)`, returning `None` to mean "not a
Databook, use the Dataset path". `KeyError`/`TypeError` are included because
Tablib raises them when a Databook-capable format (JSON/YAML) holds a
single-Dataset shape (a records list rather than `[{title, data}, ...]`).

**Why:** a static `{format: supports_databook}` table would drift from
upstream and force a tublub change every time Tablib gains a format. Genuine
load errors (corrupt files, decode failures) still propagate — the broad
catch is scoped to the capability question, not to swallowing real errors.

### Content over extension for input detection
Input format is resolved with the priority **`-f` flag > content detection >
extension** (`_resolve_input_format`). On an extension/content mismatch tublub
**warns to stderr and proceeds with the detected format**.

**Why:** extensions lie (legacy web exports routinely use `.xls` for CSV), so
content wins. But content detection isn't infallible either — Tablib's
`detect_format` leans on `csv.Sniffer`, which fails on single-column CSV/TSV
(no delimiter to sniff) — so `-f` is the escape hatch. The detection fallback
chain (`_detect_format_from_bytes`, shared by file and stdin paths) is:
binary detect -> decode to text -> text detect -> a last-resort "looks like
plain text lines" heuristic that assumes TSV (TSV over CSV so values
containing commas aren't split). This *inverted* the earlier (2024) behaviour
that trusted the extension first and only fell back to content on failure;
see [`decisions.md` 004](decisions.md).

### Injectable IO edges
Every function that touches a `sys` stream or TTY state takes an optional
keyword-only parameter defaulting to `None`, resolved to the real `sys`
object inside the body at call time — `cli(argv)`,
`parse_command_line(..., stdin_isatty=...)`, `stdin: IO[bytes]` on the stdin
loaders, `stdout: TextIO` on `_default_export_handle`. Tests inject values
instead of monkeypatching globals; no wrapper/console object (the 009
rationale), and never a `sys.*` default in the signature (it would be
captured at definition time — the 0.4.0 bug). New IO edges must follow this
pattern. See [`decisions.md` 020](decisions.md).

### Single-sheet targets never auto-split
Single-sheet output formats (csv/tsv/dbf/cli/jira/latex/sql/...) never
silently fan a multi-sheet input out into multiple files. The user must pick
a single sheet explicitly. (Relevant as the multi-sheet input roadmap lands;
see `TODO.md`.)

## Dispatch model

`cli()` is a flat four-way switch — list formats / list sheets / multi-input
Databook / single input — each delegating to a `_run_*` helper. Mode is chosen
explicitly, not by re-deriving flag combinations at each call site. A new mode
adds one branch in `cli()` plus a `_run_*`; mutual-exclusion rules live in
`_validate_args` (extract a per-flag `_validate_*` helper, as `_validate_list_sheets`
already does, rather than growing one function past the C901 cap).

## Future directions

Not commitments — possible ways the core problem (decision 000) could be
solved more fundamentally:

- **Upstream it.** Persuade Tablib's maintainers to encode the per-format
  file-open rules in Tablib itself, so tublub — and everyone else using Tablib
  for file I/O — would no longer have to own that knowledge.
- **Become a full developer-facing wrapper.** Grow tublub from a CLI into a
  library that any Python developer can use to load/save Tablib formats
  without re-reading the docs each time they add a format.
