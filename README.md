# tublub

Convert or view tabular data files — CSV, JSON, XLSX, YAML, and more — from
the command line.

tublub is a thin wrapper around [Tablib](https://github.com/jazzband/tablib).
Tablib reads and writes plenty of formats, but it won't open the files for
you — you have to know which ones need binary mode, special newline handling,
and so on. tublub bakes that per-format knowledge in, so you just point it at
a file and it works.

```text
$ tublub --list
Available formats: json xlsx xls yaml csv tsv ods dbf html jira latex rst sql cli

$ tublub input.json
Username |Identifier|First name|Last name
---------|----------|----------|---------
booker12 |9012      |Rachel    |Booker
grey07   |2070      |Laura     |Grey
jenkins46|9346      |Mary      |Jenkins
johnson81|4081      |Craig     |Johnson
smith79  |5079      |Jamie     |Smith

$ tublub input.json output.xlsx

$ file output.xlsx
output.xlsx: Microsoft Excel 2007+

$ tublub input.json --format csv
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
sheets in a single Databook (XLSX, ODS, JSON, YAML, ...); sheet names default
to each input file's stem.

To inspect a multi-sheet input without converting it, use `--list-sheets`:

```text
$ tublub --list-sheets book.xlsx
[0] people  2 rows x 2 cols
[1] cities  2 rows x 2 cols
```

Single-sheet formats (CSV, TSV, ...) print one row, using the file stem
as the title.

## News and Changes

Please see the [changelog](CHANGELOG.md) for more details.
