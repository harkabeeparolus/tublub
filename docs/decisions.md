# Decisions

Append-only log of design decisions and their rationale — the "why we did it
this way" that isn't recoverable from the code. Newest at the bottom. For the
living design overview see [`design.md`](design.md).

Each entry: a decision, the context that forced it, and why we chose as we
did. Don't edit past entries; if a decision is reversed, add a new entry that
supersedes it.

---

### 001. Content over extension for input detection; warn and continue on mismatch
*2026-05-29 · Accepted*

**Context.** A file's extension and its actual content can disagree, and
neither is fully reliable on its own.

**Decision.** Resolve input format as `-f` flag > content detection >
extension. On an extension/content mismatch, warn to stderr and proceed with
the detected format.

**Why.** Extensions lie (legacy exports use `.xls` for CSV), so content wins.
But content detection also fails — `csv.Sniffer` can't sniff single-column
CSV/TSV — so `-f` is the explicit escape hatch. Hard-failing on a mismatch
would be hostile to the common wrong-extension case; the warning makes the
ambiguity visible without blocking. (Was CR-F1.)

---

### 002. No static Tablib capability matrix; broad catch is deliberate
*2026-05-29 · Accepted*

**Context.** Only some formats support multi-sheet (Databook) load/save. We
need to know which, per operation.

**Decision.** Never hard-code a `{format: supports_databook}` table and never
add a `databook: bool` to `FormatConfig`. Attempt the Databook operation and
catch failure: `tablib.UnsupportedFormat` plus `KeyError`/`TypeError` (which
Tablib raises when a Databook-capable format holds a single-Dataset shape).
Return `None` to mean "fall back to Dataset".

**Why.** A static table drifts from upstream and forces a tublub change every
time Tablib gains a format. The broad catch is scoped to the
capability question only; genuine load errors (corrupt files, decode
failures) still propagate — confirmed by regression tests. (Was CR-B2 + the
TODO.md "capability matrix" note, now in `design.md`.)

---

### 003. Input state is `args.infiles` + `args.stdin`, not an `InputSpec`
*2026-05-29 · Accepted*

**Context.** Input state had drifted across several Namespace attributes
(`infile`, `infiles`, `stdin`), with invariants living only in comments.

**Decision.** `args.infiles: list[Path]` and `args.stdin: bool` are the only
input-state truth. Dropped the singular `args.infile`. `args.stdin` is set in
`parse_command_line` (not by argparse) and kept on `args` rather than moved to
a separate `InputSpec` dataclass.

**Why.** Two fields are easy to keep consistent; a wrapper type was more
machinery than the size of the problem warranted. (Was CR-A3, settles CR-F3.)

---

### 004. Library helpers raise `TublubError`; only the CLI edge exits
*2026-05-29 · Accepted*

**Context.** Helpers need to report user-facing problems without coupling to
the CLI.

**Decision.** Helpers raise `TublubError`; only the `_run_*` entry points
(called by `cli()`) catch it and convert to `sys.exit(msg)`. For type
narrowing, use explicit `if x is None: raise TublubError(...)` or a
narrow-return helper rather than `assert`/`cast`.

**Why.** Keeps every helper reusable outside the CLI and keeps the
exit-the-process decision at one boundary. (`assert` is also banned in `src/`
by S101.)

---

### 005. `try_load_*` fallback handshake instead of unifying on Databook
*2026-05-29 · Accepted*

**Context.** Every load path had to decide Dataset vs Databook, and the
roadmap multiplies those paths.

**Decision.** Keep both Tablib types; extract `try_load_file` /
`try_load_stdin` helpers that try Databook and fall back to Dataset, so call
sites stop reimplementing the dance. Did *not* unify everything onto Databook
internally.

**Why.** A helper for the fallback was far cheaper than changing the type
signature of most helpers, and some Tablib ops differ between the two types.
The stdin variant must try both interpretations on one read (stdin is
consume-once). (Was CR-A1.)

---

### 006. `cli()` is a flat dispatch over explicit modes
*2026-05-29 · Accepted*

**Context.** Mode used to be inferred from flag combinations scattered through
`cli()`, approaching the C901/branch caps.

**Decision.** `cli()` is a flat switch (list / list-sheets / databook /
single), one `_run_*` per mode. New modes add a branch plus a `_run_*`;
mutual-exclusion rules go in per-flag `_validate_*` helpers. Did not adopt
argparse subparsers.

**Why.** Keeps the dispatcher readable and each mode independently testable
without the bigger surface change subparsers would impose. (Was CR-A2.)

---

### 007. Keep the two empty-input messages distinct
*2026-05-29 · Accepted*

**Context.** The single-input and multi-input paths report "no data" with
different wording and triggers (`not my_data` vs `book.size == 0`).

**Decision.** Leave them distinct.

**Why.** They genuinely differ — single-input names the source it read from;
the Databook path reports across all inputs — so the wording carries real
information. (Was CR-F2.)

---

### 008. WONTFIX: manual dict counting in `_unique_titles`
*2026-05-29 · Rejected (won't change)*

**Context.** `_unique_titles` tracks collision suffixes with a manual dict;
`collections.Counter`/`defaultdict` could do the same.

**Decision.** Leave the manual counting as-is.

**Why.** Pure style preference; the current code is readable and the churn
isn't worth it. (Was CR-E1.)
