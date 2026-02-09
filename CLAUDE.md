# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is tublub?

A CLI tool that converts between tabular data formats (CSV, JSON, XLSX, YAML, etc.) using the Tablib library. Entry point: `tublub.main:cli`.

One of the main challenges with Tablib is that it does not help with auto-detection and opening files the correct way for each format. We try to handle that reliably in tublub.

## Commands

```bash
uv run tublub --list              # run the tool (show available formats)
uv run ruff check                 # lint
uv run ruff format                # auto-format
uv run mypy                       # type hints
uv run ty                         # type hints
uv run pytest                     # run tests
```

## Architecture

Single-module CLI in `src/tublub/main.py`:

- `cli()` — entry point: parse args → load input → save/export/print
- `load_dataset_file()` — detects format (Tablib detection with file-extension fallback), opens in binary/text mode as appropriate, passes format-specific extra args
- `save_dataset_file()` / `export_dataset()` — output to file or stdout; prevents binary output to TTY
- `filter_args()` — whitelists extra CLI args per format (defined in `LOAD_EXTRA_ARGS` / `SAVE_EXTRA_ARGS` / `OPEN_EXTRA_ARGS` dicts)
- `build_argument_parser()` — argparse setup with input/output option groups

## Conventions

- **Linting:** Ruff with `select = ["ALL"]`. Print statements are allowed (`T20` ignored) since this is a CLI tool.
- **Build system:** uv (`uv_build` backend)
- **Python:** >=3.10
- **Source layout:** `src/tublub/`
