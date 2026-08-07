# tublub

[![PyPI](https://img.shields.io/pypi/v/tublub)](https://pypi.org/project/tublub/)
[![Tests](https://github.com/harkabeeparolus/tublub/actions/workflows/tests.yml/badge.svg)](https://github.com/harkabeeparolus/tublub/actions/workflows/tests.yml)

Convert or view tabular data files — CSV, JSON, XLSX, YAML, and more — from
the command line.

tublub is a thin wrapper around [Tablib](https://github.com/jazzband/tablib).
Tablib reads and writes plenty of formats, but it won't open the files for
you — you have to know which ones need binary mode, special newline handling,
and so on. tublub bakes that per-format knowledge in, so you just point it at
a file and it works.

```text
$ tublub --list-formats
Available formats: json xlsx xls yaml csv tsv ods dbf html jira latex rst sql cli

$ tublub input.json
Username      Identifier  First name    Last name
booker12            9012  Rachel        Booker
grey07              2070  Laura         Grey
jenkins46           9346  Mary          Jenkins
johnson81           4081  Craig         Johnson
smith79             5079  Jamie         Smith

$ tublub input.json output.xlsx

$ file output.xlsx
output.xlsx: Microsoft Excel 2007+

$ tublub -t csv input.json
Username,Identifier,First name,Last name
booker12,9012,Rachel,Booker
grey07,2070,Laura,Grey
jenkins46,9346,Mary,Jenkins
johnson81,4081,Craig,Johnson
smith79,5079,Jamie,Smith

$ tublub -o book.xlsx sales.csv users.json regions.tsv
Saved 'book.xlsx', 3 sheets (xlsx)
```

With `-o`, all positional arguments are inputs. Two or more inputs become
sheets in a single multi-sheet file (XLSX, ODS, JSON, YAML, ...) — every sheet
of every input, so multi-sheet inputs are expanded rather than truncated.
Sheets keep their own names, and a whole-file input is named after its file
stem; names are only changed when two would collide.

An existing output file is never overwritten silently: at a terminal tublub
asks first, and in a script or a pipe it refuses, since nothing there can
answer the question. Decide up front with `-y` (always overwrite) or `-n`
(never overwrite).

Reading an existing multi-sheet workbook works the other way round: `-l` lists
its sheets, `-s` picks them by index or title, and a conversion with no
selection converts every sheet the target format can hold.

```text
$ tublub -l book.xlsx
[0] people  2 rows x 2 cols
[1] cities  2 rows x 2 cols

$ tublub -s cities book.xlsx
city          pop
Stockholm  975904
Goteborg   583056

$ tublub book.xlsx out.ods
Saved 'out.ods', 2 sheets (ods)
```

## Installation

```bash
pipx install tublub
```

or, equivalently, `uv tool install tublub`. Either one gets you the `tublub`
command; pipx (1.5 and later) additionally puts the manual page on your
manpath, so `man tublub` works.

## Documentation

The [manual page](docs/tublub.1.md) is the authoritative reference for every
flag, for sheet selection, and for what happens when a format can not hold
what you asked it to. Read it with `man tublub` once installed, and
`tublub --help` for a quick reminder of the flags.

## News and Changes

Please see the [changelog](CHANGELOG.md) for more details.
