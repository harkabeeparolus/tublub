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
just run -- ARGS  # run the CLI from the dev checkout, e.g. `just run -- --list`
```

## Architecture

Single-module CLI in `src/tublub/main.py`. Entry point: `tublub.main:cli`.
Per-format behavior (binary?, newline, allowed load/save kwargs) lives in the
`FORMATS` dict — adding or tweaking a format means editing that entry, not
sprinkling conditionals through the loaders.

## Changelog

Always update `CHANGELOG.md` under the `[Unreleased]` section when making user-facing changes (new features, bug fixes, behavior changes). Follow the [Keep a Changelog](https://keepachangelog.com) format with `Added`, `Changed`, `Fixed`, `Removed` subsections.

## Conventions

- Print statements are allowed (`T20` ignored in Ruff config) since this is a CLI tool.
- Library helpers raise `TublubError` for user-facing problems; only `cli()`
  catches it and converts to `sys.exit(msg)`. Keep new helpers consistent so
  they remain reusable outside the CLI.

## Ruff gotchas

- RUF001/2/3 flag ambiguous Unicode (e.g. `×`, `−`, `–`) in strings, comments, and docstrings — use ASCII equivalents.
- C901/PLR0912 cap functions at ~10 cyclomatic / ~12 branches — extract a helper before piling more guards into `_validate_args` or `cli`.
- S101 forbids `assert` in `src/` (tests get it via per-file-ignores). For type narrowing, use an explicit `if x is None: raise TublubError(...)` instead.
- D301 rejects backslashes in docstrings — spell out characters (e.g. "backslash") or prefix the docstring with `r"""`.

## Testing patterns

- Argparse unit tests: call `parse_command_line(argv)` directly and assert on the returned `args`.
- CLI integration tests: `monkeypatch.setattr(sys, "argv", [...])`, call `cli()`, read `capsys.readouterr().out`.
- Rejection tests use `pytest.raises(SystemExit)` since `parser.error()` exits.
