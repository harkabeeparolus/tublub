# tublub

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

## Multi-sheet input

Three rules cover the whole surface:

1. **`-s/--sheet` picks sheets; selection never changes where output may go.**
   One selected sheet behaves exactly like a single-sheet input does; several
   behave like a multi-sheet workbook — printed with headings, saved with `-o`,
   exported with `-t` — wherever the output format can hold multiple sheets.
   `--all-sheets` is sugar for "select everything".
2. **You can select exactly what `-l/--list-sheets` shows.** Indexed lines
   (`[0] people ...`) are selectable by index or title; a bare line means the
   input has no sheet structure and nothing to select.
3. **Commas are for index lists; repeat `-s` for names; `name:` forces a
   title.** So `-s 0,2` takes two indices, `-s people -s cities` takes two
   titles, and `-s name:2024` picks the sheet *titled* `2024` rather than
   index 2024.

`-l/--list-sheets` inspects an input without converting it:

```text
$ tublub -l book.xlsx
[0] people  2 rows x 2 cols
[1] cities  2 rows x 2 cols

$ tublub -l people.csv
2 rows x 2 cols
```

An input without sheet structure (CSV, TSV, records-shaped JSON, ...) prints
one bare `N rows x M cols` line — there is no index or title to select.

Pick one sheet and it prints like any single-sheet file; pick several and each
gets a heading:

```text
$ tublub -s cities book.xlsx
city          pop
Stockholm  975904
Goteborg   583056

$ tublub -s 0,1 book.xlsx
=== people (2 rows) ===
name      age
Alice      30
Bob        41

=== cities (2 rows) ===
city          pop
Stockholm  975904
Goteborg   583056
```

Converting without any selection converts *every* sheet, as long as the target
format can hold them:

```text
$ tublub book.xlsx out.ods
Saved 'out.ods', 2 sheets (ods)
```

Single-sheet formats (CSV, TSV, DBF, ...) get the first sheet and always say
so on stderr, even when stderr is redirected — tublub never splits one input
across several output files:

```text
$ tublub -t csv book.xlsx
book.xlsx: format 'csv' cannot hold all 2 sheets; converting only the first (use -s to choose)
name,age
Alice,30
Bob,41
```

Asking for every sheet explicitly stays strict: `--all-sheets -o out.csv`
errors instead of quietly dropping data.

All of this works on piped input too, either as an explicit `-` or implicitly
whenever stdin is not a terminal:

```text
$ cat book.xlsx | tublub -l -
[0] people  2 rows x 2 cols
[1] cities  2 rows x 2 cols
```

## News and Changes

Please see the [changelog](CHANGELOG.md) for more details.
