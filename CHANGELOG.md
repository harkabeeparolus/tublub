# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com),
and this project adheres to [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added

* Multi-input → single Databook output. Use `-o/--output FILE` with two or more
  input files to build a multi-sheet workbook (e.g. XLSX, ODS, JSON, YAML).
  Sheet names default to each input file's stem; duplicate stems get `_2`, `_3`,
  ... suffixes. Example:
  `tublub -o book.xlsx sales.csv users.json regions.tsv`

## [0.4.1] - 2026-02-09

### Changed

* Updated Python publish workflow to use uv for building.

## [0.4.0] - 2026-02-09

### Added

* All extra format options for importing and exporting Excel, CSV, TSV, and CLI.
* Stdin pipeline support: read from stdin via `-` argument or implicitly when piped,
  with auto-detection and `-f`/`--in-format` override.
* `-f`/`--in-format` flag now works for file inputs too, as an escape hatch for
  undetectable formats.
* Fall back to file extension when Tablib content detection fails.
* Single-column text heuristic for detecting CSV/TSV when `detect_format()` fails
  (e.g. single-column data where `csv.Sniffer` can't find a delimiter).
* Test suite with pytest.
* Type hints on all functions, with mypy and ty as dev dependencies.

### Changed

* Content-based format detection now tries binary mode first, then text mode,
  catching lying extensions (e.g. `.xls` files that actually contain CSV).
* Library functions raise `TublubError` instead of calling `sys.exit()`, making
  them reusable outside the CLI.
* Correct handling of `open(..., newline="")` for reading and writing CSV files.
* Switched build system to uv.
* Minimum Python version is now 3.10.
* Use `Path` objects throughout instead of built-in `open()`.
* Improved command-line help text.

### Fixed

* Binary export to piped stdout now uses `sys.stdout.buffer` instead of crashing.
* Format detection for extensionless files no longer crashes with
  `UnicodeDecodeError` on binary files.
* `--no-headers` and `--no-xlsx-optimize` no longer silently inject default values
  into format arguments.
* Fixed `export_dataset()` evaluating `sys.stdout` at definition time instead of
  call time.

## [0.3.0] - 2022-07-29

### Added

* Extra format detection with Tablib before loading file.

### Changed

* Added *headers* for TSV format as well as CSV.
* Improved console handling for printing to stdout.

### Removed

* Pandas is no longer included, since DataFrames is not a file format.
  It also reduces the installation size on disk.

## [0.2.0] - 2022-07-29

### Added

* Warn and exit on empty input or missing input file.
* Added `--version` flag.

### Changed

* Better heuristics for guessing text or binary file format.
* Filter keyword arguments for `load()` to include only arguments that are valid
  for the current input format.

## [0.1.0] - 2022-07-28

* Initial working version.
* Not feature complete.
