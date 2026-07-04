# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is tublub?

A CLI tool that converts between tabular data formats (CSV, JSON, XLSX, YAML, etc.) using the Tablib library.

## Commands

Always run `just lint` after every complete file edit. See `Justfile` for all recipes.

```bash
just lint       # ruff check --fix + ruff format
just typecheck  # mypy + ty
just test       # pytest
just check      # all of the above
just run ARGS  # run the CLI from the dev checkout, e.g. `just run --list`
```

## Architecture

Single-module CLI in `src/tublub/main.py`. Entry point: `tublub.main:cli`.
Per-format behavior (binary?, newline, allowed load/save kwargs) lives in the
`FORMATS` dict — adding or tweaking a format means editing that entry, not
sprinkling conditionals through the loaders.

For the design rationale (detection policy, Dataset-vs-Databook split, the
"no static capability matrix" principle, error boundary) read `docs/design.md`
and the decision log in `docs/decisions.md` *before* changing format detection,
error handling, or the load/save split. `docs/TODO.md` is the multi-sheet
feature roadmap.

## Changelog

Always update `CHANGELOG.md` under the `[Unreleased]` section when making user-facing changes (new features, bug fixes, behavior changes). Follow the [Keep a Changelog](https://keepachangelog.com) format with `Added`, `Changed`, `Fixed`, `Removed` subsections.

## Conventions

- Print statements are allowed (`T20` ignored in Ruff config) since this is a CLI tool.
- Library helpers raise `TublubError` for user-facing problems; only `cli()`
  catches it and converts to `sys.exit(msg)`. Keep new helpers consistent so
  they remain reusable outside the CLI.
- User-facing strings (errors, warnings, hints, `--help`, README) never name
  Tablib internals like `Dataset`/`Databook` — say "sheet(s)"/"multi-sheet"
  (decision 019). Internal names are fine in code, docstrings, and dev docs.

## Ruff gotchas

- RUF001/2/3 flag ambiguous Unicode (e.g. `×`, `−`, `–`) in strings, comments, and docstrings — use ASCII equivalents.
- SIM108 turns `if/else` value-assignment into a ternary; if the ternary would nest ugly, build a base value then mutate it (e.g. `mode = "w" if write else "r"; if binary: mode += "b"`) instead of fighting it.
- C901/PLR0912 cap functions at ~10 cyclomatic / ~12 branches — extract a helper before piling more guards into `_validate_args` or `cli`.
- S101 forbids `assert` in `src/` (tests get it via per-file-ignores). For type narrowing, use an explicit `if x is None: raise TublubError(...)` instead, or extract a helper whose return type is already narrow (see `_default_export_handle`) rather than reaching for `typing.cast`.
- D301 rejects backslashes in docstrings — spell out characters (e.g. "backslash") or prefix the docstring with `r"""`.

## Testing patterns

- Verifying CLI error paths: `just run` swallows stderr and only reports the exit code on failure. Run `uv run tublub ARGS` directly to see the actual `parser.error`/`sys.exit` message.
- Argparse unit tests: call `parse_command_line(argv)` directly and assert on the returned `args`.
- CLI integration tests: call `cli([...])` with an argv list, read `capsys.readouterr().out`.
- Don't monkeypatch `sys` globals — the IO edges take injection params (decision 020):
  `parse_command_line(argv, stdin_isatty=True/False)` for input-presence/implicit-stdin
  paths, `stdin=io.BytesIO(...)` for the stdin loaders, `stdout=` for
  `_default_export_handle`.
- Rejection tests use `pytest.raises(SystemExit)` since `parser.error()` exits.
