# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com),
and this project adheres to [Semantic Versioning](https://semver.org).

## [Unreleased]

## [0.7.0] - 2026-08-06

### Added

* `-y/--yes` and `-n/--no-clobber`: decide up front what happens when the
  output file already exists. `-y` overwrites without asking, `-n` refuses and
  exits non-zero. The two can not be combined. Example:
  `tublub -y -o out.xlsx sales.csv`

### Changed

* **Breaking:** an existing output file is no longer overwritten silently. At a
  terminal tublub asks first (`Overwrite? [y/N]`, question on stderr since
  stdout may be the data stream, default no); when stdin is not a terminal —
  scripts, pipes, automation — it refuses with an error suggesting `-y`, since
  nothing there can answer the question. Pass `-y` for the previous behaviour.
  This guards the `[INFILE [OUTFILE]]` form in particular, where
  `tublub -s 0 a.xlsx b.csv` meant as two inputs used to rewrite `b.csv`.
* Converting a single input that has no sheet structure to a format that carries
  sheet names (XLSX, ODS, XLS) now names the sheet after the input instead of
  `Tablib Dataset`: `tublub customers.csv out.xlsx` writes a sheet named
  `customers`, and piped input writes one named `stdin`. This is the name
  multi-input mode already gave it, so adding or dropping a second input no
  longer changes what the first one's sheet is called. Sheet names that came
  with the input are still kept verbatim.

### Fixed

* A multi-sheet save to a format that can not hold several sheets no longer
  empties the output file. `tublub --all-sheets -o out.csv book.xlsx` used to
  truncate `out.csv` to 0 bytes before reporting that csv does not support
  multi-sheet output; the file is now left exactly as it was, and a file that
  did not exist is not created.
* An input file whose extension does not match its content (e.g. CSV data in
  a `.xls` file) printed the "Extension suggests ... but content detected
  as ..." warning twice and was read up to four times; it is now read once
  and the warning is printed once.

## [0.6.0] - 2026-08-05

### Added

* `-s/--sheet SEL`: select sheet(s) from a multi-sheet input by 0-based index
  or title. `-s 0,2` picks an index list, repeating `-s` picks several titles,
  and `name:2024` forces a title match for numeric-looking titles. One selected
  sheet behaves exactly like a single-sheet input (print, `-o`, `-t`); several
  selected sheets print with `=== title (N rows) ===` headings, save with `-o`,
  or export with `-t` wherever the output format supports multi-sheet output
  (otherwise the error suggests picking one sheet). Example:
  `tublub -s Users -s 2 book.xlsx`
* `--all-sheets`: select every sheet of a multi-sheet input; on an input
  without sheet structure it changes nothing. Example:
  `tublub --all-sheets -o out.json book.xlsx`
* `-l/--list-sheets`, `-s/--sheet`, and `--all-sheets` now work on piped
  input, both as an explicit `-` and implicitly when stdin is not a terminal.
  Piped data is read exactly like a file argument, so
  `cat book.xlsx | tublub -s Users -` behaves like
  `tublub -s Users book.xlsx`. Combining several inputs still rejects `-`.
* Combining several inputs into one workbook now expands *every* sheet of
  every input, keeping the original sheet names:
  `tublub -o merged.xlsx book.xlsx sales.csv` gives one sheet per sheet of
  `book.xlsx` plus a `sales` sheet. Previously a multi-sheet input
  contributed only its first sheet, and a JSON/YAML workbook contributed a
  garbled two-column `title`/`data` sheet. Names are only changed when two
  sheets would collide: a sheet then takes its workbook's filename
  (`book__Users`), a whole-file sheet its parent directory (`hr_people`),
  with a `_2`/`_3` suffix if that still collides and truncation to 31
  characters for XLSX. Any renaming is reported on stderr.

### Changed

* **Breaking:** `-l` now lists the *sheets* in an input file (was
  `--list-sheets`); it is the short form for the everyday operation.
  Listing the supported *formats* moves to the long-only `--list-formats`.
  The bare `--list` spelling is gone — it now errors as an ambiguous option
  (it could mean either new flag), which is the migration hint.
* **Breaking:** the input/output format flags gain pandoc's long names,
  `-f/--from` and `-t/--to`. The old long forms `--in-format` and `--format`
  are removed and now error as unrecognized arguments; the short flags `-f`
  and `-t` are unchanged.
* **Breaking:** `-l/--list-sheets` on an input without sheet structure (e.g.
  CSV, or JSON shaped as a list of records) now prints one bare
  `N rows x M cols` line instead of a made-up `[0] {filename}` entry. An
  indexed line now always means a real, selectable sheet.
* `--help` now lists the available formats in its epilog, so format discovery
  no longer requires `--list-formats`.
* Error messages and `--help` text no longer mention Tablib's internal
  `Databook` type; they say "multi-sheet" instead (e.g. "Format 'csv' does
  not support multi-sheet output").
* The table printed to the terminal by default now uses the same renderer as
  `-t cli` (Tabulate, in its default `plain` style), so `tublub data.csv` and
  `tublub -t cli data.csv` produce identical output. `--tablefmt` styles both;
  previously it only had effect together with `-t cli`. Installations where the
  `cli` format is unavailable fall back to the previous built-in table.
* Text output written to stdout now ends with a newline, so the shell prompt no
  longer starts on the last line of output. Files written with `-o` are
  byte-for-byte unchanged.
* **Breaking:** converting a multi-sheet input now converts *every* sheet by
  default. `tublub book.xlsx out.ods` and `tublub -t json book.xlsx` write the
  whole workbook instead of silently keeping only the first sheet — matching
  what `--all-sheets` does, and what multi-input `-o` has always done, so
  adding or dropping a second input no longer changes how the first one is
  read. Output formats that cannot hold several sheets (CSV, TSV, DBF, `cli`,
  ...) still get the first sheet, but now always say so on stderr, even when
  stderr is redirected:
  `book.xlsx: format 'csv' cannot hold all 2 sheets; converting only the first (use -s to choose)`.
  Scripts that relied on first-sheet-only conversion, or that need an output
  shape independent of the input's sheet count, should pin `-s 0`. Asking for
  every sheet explicitly stays strict: `--all-sheets` and multi-sheet `-s`
  selections still error where the default falls back.
* Printing a multi-sheet input to the terminal still shows its first sheet, and
  now points at the others on stderr when stderr is a terminal:
  `book.xlsx: 1 more sheet(s) — see -l to list, -s to pick, --all-sheets for all`.
  The note is suppressed when stderr is redirected or piped, so scripted
  pipelines stay quiet. One-sheet inputs and inputs without sheet structure are
  unchanged and print nothing extra.

### Fixed

* A one-sheet JSON or YAML *workbook* (`[{"title": ..., "data": [...]}]`) now
  renders its sheet, instead of a two-column `title`/`data` table of the raw
  workbook wrapper.
* Piped input is read exactly like a file argument, so
  `cat book.xlsx | tublub -f xlsx -o out.ods` no longer drops the sheets that
  `tublub book.xlsx -o out.ods` keeps.

## [0.5.0] - 2026-05-29

### Added

* Multi-input → single Databook output. Use `-o/--output FILE` with two or more
  input files to build a multi-sheet workbook (e.g. XLSX, ODS, JSON, YAML).
  Sheet names default to each input file's stem; on collisions the parent
  directory name qualifies the title (e.g. `data/a.csv` and `backup/a.csv`
  become `data_a` and `backup_a`), with `_2`, `_3`, ... suffixes as a final
  fallback. Example:
  `tublub -o book.xlsx sales.csv users.json regions.tsv`
* `--list-sheets` flag: print sheet titles with row and column counts for
  multi-sheet inputs (XLSX, ODS, JSON, YAML), or one line for single-sheet
  formats. Example: `tublub --list-sheets book.xlsx`

### Changed

* Sheet-title disambiguation for multi-input Databook output now prefers the
  parent directory name over a numeric suffix when input stems collide, and
  prints a stderr note when disambiguation happens.
* Multi-sheet titles are now clamped to 31 characters (the XLSX worksheet-title
  limit), with disambiguation suffixes trimmed to fit inside the limit, so
  generated workbooks no longer trigger openpyxl's "Title is more than 31
  characters" warning and stay readable in all applications.

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
