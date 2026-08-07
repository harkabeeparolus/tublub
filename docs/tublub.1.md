---
title: TUBLUB
section: 1
header: General Commands Manual
---
<!-- markdownlint-disable single-h1 -->

# NAME

**tublub** — convert or view tabular data files

# SYNOPSIS

**tublub**
\[**-f** *FMT*]
\[**-t** *FMT*]
\[*INFILE* \[*OUTFILE*]]

**tublub**
**-o** *FILE*
\[*INFILE* ...]

**tublub**
**-l**
\[*INFILE*]

**tublub**
\[**-s** *SEL* | **--all-sheets**]
\[*INFILE* \[*OUTFILE*]]

# DESCRIPTION

**tublub** converts tabular data files between formats — CSV, TSV, JSON,
YAML, XLSX, XLS, ODS, DBF, HTML and more — and pretty-prints them as a table
when no output file is given. It is a thin wrapper around the Python Tablib
library; **tublub** supplies the per-format knowledge Tablib leaves to its
caller, such as which formats are binary and how their files must be opened.

An input is read from *INFILE*, or from standard input when *INFILE* is `-`
or when standard input is not a terminal. Output goes to *OUTFILE*, to the
file named by **-o**, or to standard output.

Both formats are normally detected rather than declared. The input format is
detected from the file contents, falling back to the file extension; when the
two disagree, **tublub** says so on standard error and trusts the contents.
The output format comes from the *OUTFILE* extension, or from **-t**, or —
printing to a terminal with neither — defaults to a rendered table
(the `cli` format). Use **-f** and **-t** to override either end, for example
on a `.txt` file or a single-column CSV, where content detection has nothing
to go on.

Printing a binary format to a terminal is refused rather than garbling the
screen; redirect it or name an output file. Run **tublub --list-formats** for
the formats the installed Tablib supports.

# OPTIONS

**-h**, **--help**
:   Show a help message and exit.

**-V**, **--version**
:   Show the program version and exit.

**--list-formats**
:   List the available file formats and exit.

**--dialect** *DIALECT*
:   For CSV, the input and output dialect: `excel` or `unix`.

**-d**, **--delimiter** *C*
:   For CSV, the input and output field delimiter.

**-q**, **--quotechar** *C*
:   For CSV, the input and output quote character.

## Input options

**-H**, **--no-headers**
:   The CSV/TSV input data has no header row.

**--skip-lines** *LINES*
:   For CSV/TSV/XLS/XLSX input, skip this many lines at the top.

**--no-xlsx-optimize**
:   Disable optimized (`read_only`) loading of XLSX files. Slower, but it
    copes with workbooks the optimized reader mishandles.

**-f**, **--from** *FMT*
:   Override the input format, for example on a `.txt` file or content that
    cannot be detected.

**-l**, **--list-sheets**
:   List the sheets in the input and exit. See **SHEET SELECTION**.

**-s**, **--sheet** *SEL*
:   Select sheets by 0-based index or by title. See **SHEET SELECTION**.

**--all-sheets**
:   Select every sheet of a multi-sheet input. On an input with no sheet
    structure this changes nothing.

## Output options

**-t**, **--to** *FMT*
:   Output format. Defaults to the *OUTFILE* extension, or to a rendered
    table when printing to a terminal.

**-o**, **--output** *FILE*
:   Write to *FILE*. With **-o**, every positional argument is an input, and
    two or more inputs are combined into one multi-sheet file.

**-y**, **--yes**
:   Overwrite an existing output file without asking.

**-n**, **--no-clobber**
:   Never overwrite an existing output file; refuse instead. Can not be
    combined with **-y**.

**--tablefmt** *TABLEFMT*
:   For table output, the Tabulate table format to render with, for example
    `fancy_grid` or `github`.

# SHEET SELECTION

Three rules cover the whole surface.

1.  **-s**/**--sheet** picks sheets, and selection never changes where output
    may go. One selected sheet behaves exactly like a single-sheet input does;
    several behave like a multi-sheet workbook — printed with headings, saved
    with **-o**, exported with **-t** — wherever the output format can hold
    multiple sheets. **--all-sheets** is sugar for selecting everything.

2.  You can select exactly what **-l**/**--list-sheets** shows. Indexed lines
    (`[0] people  2 rows x 2 cols`) are selectable by index or by title. A
    bare `N rows x M cols` line means the input has no sheet structure and
    nothing to select — CSV, TSV and records-shaped JSON or YAML all look
    like this.

3.  Commas are for index lists, repeated **-s** is for names, and `name:`
    forces a title. So `-s 0,2` takes two indices, `-s people -s cities`
    takes two titles, and `-s name:2024` picks the sheet *titled* `2024`
    rather than index 2024.

# OUTPUT FILES

An existing output file is never overwritten silently. At a terminal
**tublub** asks first, with the question on standard error since standard
output may be the data stream; anywhere else — a script, a pipe, an
automated run — it refuses, since nothing there can answer the question.
Decide up front with **-y** or **-n**.

A multi-sheet save that the output format can not hold leaves the output file
untouched rather than truncating it: the workbook is rendered in full before
the file is opened.

# MULTI-SHEET OUTPUT

With **-o** and two or more inputs, every sheet of every input becomes a
sheet of the output file, so multi-sheet inputs are expanded rather than
truncated. Sheets keep their own names; an input with no sheet structure is
named after its file stem, or `stdin` when it was piped in. Names are only
changed when two would collide, and **tublub** reports on standard error when
it changes one.

Converting a multi-sheet input without any selection converts *every* sheet,
as long as the target format can hold them (XLSX, ODS, XLS, JSON, YAML, HTML
and RST can; CSV, TSV, DBF and the other single-sheet formats can not). A
target that can not hold them gets the first sheet plus a warning on standard
error, even when standard error is redirected — dropping data is something a
script has to be able to see. **tublub** never splits one input across
several output files.

Asking for every sheet explicitly stays strict: **--all-sheets** with a
single-sheet output format is an error rather than a quiet loss of data.

Printing a multi-sheet input with no selection shows its first sheet, and at
a terminal adds a note that more sheets are there.

# EXAMPLES

Pretty-print a file as a table:

    $ tublub input.json
    Username      Identifier  First name    Last name
    booker12            9012  Rachel        Booker
    grey07              2070  Laura         Grey
    jenkins46           9346  Mary          Jenkins
    johnson81           4081  Craig         Johnson
    smith79             5079  Jamie         Smith

Convert a file, with the output format taken from the extension:

    $ tublub input.json output.xlsx
    $ file output.xlsx
    output.xlsx: Microsoft Excel 2007+

Convert to standard output in a named format:

    $ tublub -t csv input.json
    Username,Identifier,First name,Last name
    booker12,9012,Rachel,Booker
    grey07,2070,Laura,Grey
    jenkins46,9346,Mary,Jenkins
    johnson81,4081,Craig,Johnson
    smith79,5079,Jamie,Smith

Combine several inputs into one workbook:

    $ tublub -o book.xlsx sales.csv users.json regions.tsv
    Saved 'book.xlsx', 3 sheets (xlsx)

List the sheets of an input without converting it. A file with sheets gets an
indexed line each; one without gets a single bare line:

    $ tublub -l book.xlsx
    [0] people  2 rows x 2 cols
    [1] cities  2 rows x 2 cols

    $ tublub -l people.csv
    2 rows x 2 cols

Pick one sheet and it prints like any single-sheet file:

    $ tublub -s cities book.xlsx
    city          pop
    Stockholm  975904
    Goteborg   583056

Pick several and each gets a heading:

    $ tublub -s 0,1 book.xlsx
    === people (2 rows) ===
    name      age
    Alice      30
    Bob        41

    === cities (2 rows) ===
    city          pop
    Stockholm  975904
    Goteborg   583056

Convert every sheet to another multi-sheet format:

    $ tublub book.xlsx out.ods
    Saved 'out.ods', 2 sheets (ods)

A single-sheet target gets the first sheet, and says so:

    $ tublub -t csv book.xlsx
    book.xlsx: format 'csv' cannot hold all 2 sheets; converting only the first (use -s to choose)
    name,age
    Alice,30
    Bob,41

Piped input works the same way, as an explicit `-` or implicitly whenever
standard input is not a terminal:

    $ cat book.xlsx | tublub -l -
    [0] people  2 rows x 2 cols
    [1] cities  2 rows x 2 cols

# EXIT STATUS

0
:   Success.

1
:   The run failed — an unreadable or undetectable input, no data loaded, an
    output format that can not hold the selected sheets, a refused overwrite,
    or a binary format aimed at a terminal. The reason is printed on standard
    error.

2
:   The command line itself was rejected, for example an unknown flag or a
    combination that is not allowed.

# SEE ALSO

Project home and issue tracker: <https://github.com/harkabeeparolus/tublub>

Tablib, the library doing the reading and writing:
<https://tablib.readthedocs.io>
