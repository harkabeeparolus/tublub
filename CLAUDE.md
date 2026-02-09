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
```

## Architecture

Single-module CLI in `src/tublub/main.py`. Entry point: `tublub.main:cli`.

## Changelog

Always update `CHANGELOG.md` under the `[Unreleased]` section when making user-facing changes (new features, bug fixes, behavior changes). Follow the [Keep a Changelog](https://keepachangelog.com) format with `Added`, `Changed`, `Fixed`, `Removed` subsections.

## Conventions

- Print statements are allowed (`T20` ignored in Ruff config) since this is a CLI tool.
