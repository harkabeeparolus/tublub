# tublub

Convert or view tabular data files using [Tablib](https://github.com/jazzband/tablib).
Tublub is just a simple CLI wrapper around Tablib.

```text
$ tublub --list
Available formats: json xlsx xls yaml csv tsv ods dbf html jira latex df rst cli

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

## News and Changes

Please see the [changelog](CHANGELOG.md) for more details.
