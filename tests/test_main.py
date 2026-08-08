"""Tests for tublub.main."""

import io
import json
import re
from pathlib import Path

import pytest
import tablib

from tublub.main import (
    FORMATS,
    XLSX_TITLE_LIMIT,
    MultiSheetUnsupportedError,
    TublubError,
    _default_export_handle,
    _looks_like_text_lines,
    _unique_titles,
    build_argument_parser,
    build_databook,
    cli,
    export_databook,
    export_dataset,
    filter_args,
    get_formats,
    guess_file_format,
    is_bin,
    load_databook_file,
    load_databook_stdin,
    load_dataset_file,
    load_dataset_stdin,
    parse_command_line,
    save_databook_file,
    save_dataset_file,
    try_load_file,
    try_load_stdin,
)

# --- guess_file_format ---


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("data.csv", "csv"),
        ("data.json", "json"),
        ("data.xlsx", "xlsx"),
        ("report.yaml", "yaml"),
        ("data.tsv", "tsv"),
    ],
)
def test_known_extensions(filename, expected):
    assert guess_file_format(Path(filename)) == expected


@pytest.mark.parametrize("filename", ["data.xyz", "datafile"])
def test_unknown_or_missing_extension(filename):
    assert guess_file_format(Path(filename)) is None


def test_none_input():
    assert guess_file_format(None) is None


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("OUT.JSON", "json"),
        ("Data.Csv", "csv"),
    ],
)
def test_uppercase_extensions(filename, expected):
    assert guess_file_format(Path(filename)) == expected


def test_cli_uppercase_output_extension(sample_csv, tmp_path):
    out = tmp_path / "OUT.JSON"
    assert cli([str(sample_csv), str(out)]) == 0
    assert json.loads(out.read_text())[0]["name"] == "Alice"


def test_uppercase_extension_mismatch_warns(tmp_path, capsys):
    p = tmp_path / "data.XLS"
    p.write_text("name,age\nAlice,30\nBob,25\n")
    try_load_file(p, extra_args={})
    assert "Extension suggests xls" in capsys.readouterr().err


# --- is_bin ---


@pytest.mark.parametrize("fmt", sorted(k for k, v in FORMATS.items() if v.binary))
def test_binary_formats(fmt):
    assert is_bin(fmt) is True


@pytest.mark.parametrize("fmt", ["csv", "tsv", "json", "yaml", "html"])
def test_text_formats(fmt):
    assert is_bin(fmt) is False


def test_none():
    assert is_bin(None) is False


def test_is_bin_empty():
    assert is_bin("") is False


# --- filter_args ---


def test_filters_to_matching_format():
    user_args = {"skip_lines": 2, "delimiter": ","}
    result = filter_args("load", user_args, "csv")
    assert result == {"skip_lines": 2, "delimiter": ","}


def test_excludes_irrelevant_args():
    user_args = {"skip_lines": 2, "delimiter": ","}
    result = filter_args("load", user_args, "xlsx")
    assert result == {"skip_lines": 2}
    assert "delimiter" not in result


def test_unknown_format_returns_empty():
    user_args = {"skip_lines": 2}
    result = filter_args("load", user_args, "json")
    assert result == {}


def test_none_values_excluded():
    user_args = {"skip_lines": None, "delimiter": ","}
    result = filter_args("load", user_args, "csv")
    assert result == {"delimiter": ","}


def test_empty_user_args():
    result = filter_args("load", {}, "csv")
    assert result == {}


def test_save_extra_args():
    user_args = {"tablefmt": "fancy_grid"}
    result = filter_args("save", user_args, "cli")
    assert result == {"tablefmt": "fancy_grid"}


# --- get_formats ---


def test_returns_tuple():
    assert isinstance(get_formats(), tuple)


def test_includes_common_formats():
    formats = get_formats()
    for fmt in ("csv", "json", "xlsx", "yaml", "tsv"):
        assert fmt in formats


def test_cached():
    assert get_formats() is get_formats()


# --- _looks_like_text_lines ---


# Unit tests for the single-column text heuristic.


def test_single_column_data():
    assert _looks_like_text_lines("name\nAlice\nBob\n") is True


def test_single_line_rejected():
    assert _looks_like_text_lines("hello") is False


def test_empty_string_rejected():
    assert _looks_like_text_lines("") is False


def test_whitespace_only_rejected():
    assert _looks_like_text_lines("  \n  \n") is False


@pytest.mark.parametrize("delimiter", [",", "\t", ";", "|"])
def test_delimited_data_rejected(delimiter):
    text = f"a{delimiter}b\n1{delimiter}2\n"
    assert _looks_like_text_lines(text) is False


def test_prose_with_commas_rejected():
    assert _looks_like_text_lines("Hello, world.\nDear sir, ...\n") is False


# --- load_dataset_file ---


@pytest.mark.parametrize(
    "fixture",
    ["sample_csv", "sample_json", "sample_tsv", "sample_yaml"],
)
def test_load_formats(fixture, request):
    path = request.getfixturevalue(fixture)
    ds = load_dataset_file(path, extra_args={})
    assert len(ds) == 2
    assert ds.headers is not None
    assert "name" in ds.headers


def test_load_csv_with_skip_lines(tmp_path):
    p = tmp_path / "skip.csv"
    p.write_text("# comment\nname,age\nAlice,30\n")
    ds = load_dataset_file(p, extra_args={"skip_lines": 1})
    assert len(ds) == 1
    assert ds.headers == ["name", "age"]


def test_load_csv_with_delimiter(tmp_path):
    p = tmp_path / "semi.csv"
    p.write_text("name;age\nAlice;30\n")
    ds = load_dataset_file(p, extra_args={"delimiter": ";"})
    assert len(ds) == 1
    assert ds.headers == ["name", "age"]


def test_load_csv_no_extension(tmp_path):
    """CSV file without extension should be detected via text-mode fallback."""
    p = tmp_path / "data"
    p.write_text("name,age,city\nAlice,30,Stockholm\nBob,25,Gothenburg\n")
    ds = load_dataset_file(p, extra_args={})
    assert len(ds) == 2
    assert ds.headers == ["name", "age", "city"]


def test_load_xlsx_no_extension(tmp_path, sample_data):
    """XLSX file without extension should be detected via binary-mode pass."""
    p = tmp_path / "data"
    p.write_bytes(sample_data.export("xlsx"))
    ds = load_dataset_file(p, extra_args={})
    assert len(ds) == 2


def test_load_single_column_txt(tmp_path):
    """Single-column data in a .txt file should be detected via heuristic."""
    p = tmp_path / "names.txt"
    p.write_text("name\nAlice\nBob\n")
    ds = load_dataset_file(p, extra_args={})
    assert len(ds) == 2
    assert ds.headers == ["name"]


def test_load_single_column_no_extension(tmp_path):
    """Single-column data without extension should be detected via heuristic."""
    p = tmp_path / "data"
    p.write_text("name\nAlice\nBob\n")
    ds = load_dataset_file(p, extra_args={})
    assert len(ds) == 2
    assert ds.headers == ["name"]


def test_load_in_format_overrides_detection(tmp_path):
    """-f flag should override both detection and extension."""
    p = tmp_path / "data.txt"
    p.write_text("name,age\nAlice,30\n")
    ds = load_dataset_file(p, extra_args={}, in_format="csv")
    assert ds.headers == ["name", "age"]


def test_load_unknown_format_raises(tmp_path):
    p = tmp_path / "data.xyz"
    p.write_text("not a known format")
    with pytest.raises(TublubError, match="Unable to detect"):
        load_dataset_file(p, extra_args={})


# --- save_dataset_file ---


@pytest.mark.parametrize("fmt", ["csv", "json", "yaml"])
def test_save_formats(sample_data, tmp_path, fmt):
    out = tmp_path / f"out.{fmt}"
    save_dataset_file(sample_data, out, extra_args={})
    assert "Alice" in out.read_text()


def test_save_dataset_unknown_format_raises(sample_data, tmp_path):
    out = tmp_path / "out.xyz"
    with pytest.raises(TublubError, match="Unable to detect"):
        save_dataset_file(sample_data, out, extra_args={})


def test_roundtrip_csv(sample_data, tmp_path):
    out = tmp_path / "roundtrip.csv"
    save_dataset_file(sample_data, out, extra_args={})
    loaded = load_dataset_file(out, extra_args={})
    assert loaded.headers == sample_data.headers
    assert len(loaded) == len(sample_data)


def test_failed_export_leaves_existing_file_intact(tmp_path):
    out = tmp_path / "out.dbf"
    out.write_text("sentinel")
    headerless = tablib.Dataset()  # dbf cannot export a headerless dataset
    headerless.append(["Alice", 30])
    with pytest.raises(TublubError, match="dbf"):
        save_dataset_file(headerless, out, extra_args={})
    assert out.read_text() == "sentinel"


# --- export_dataset ---


def test_export_to_file_handle(sample_data, tmp_path):
    out = tmp_path / "export.csv"
    with out.open("w", newline="") as fh:
        export_dataset(sample_data, "csv", extra_args={}, file_handle=fh)
    content = out.read_text()
    assert "Alice" in content


def test_default_handle_binary_to_tty_raises():
    class TTYStdout(io.TextIOWrapper):
        def isatty(self):
            return True

    with pytest.raises(TublubError, match="binary"):
        _default_export_handle("xlsx", stdout=TTYStdout(io.BytesIO()))


def test_default_handle_binary_to_piped_stdout(sample_data):
    """Binary export to non-TTY stdout should use stdout.buffer."""
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw)  # kept alive: GC would close raw
    handle = _default_export_handle("xlsx", stdout=stdout)
    export_dataset(sample_data, "xlsx", extra_args={}, file_handle=handle)
    assert raw.getvalue().startswith(b"PK")  # XLSX is a zip container


def test_default_handle_text_returns_stream():
    stream = io.StringIO()
    assert _default_export_handle("json", stdout=stream) is stream


def test_export_text_to_non_tty(sample_data, tmp_path):
    out = tmp_path / "piped.json"
    with out.open("w") as fh:
        export_dataset(sample_data, "json", extra_args={}, file_handle=fh)
    assert "Alice" in out.read_text()


def test_export_dataset_wraps_tablib_failure():
    headerless = tablib.Dataset()
    headerless.append(["Alice", 30])
    with pytest.raises(TublubError, match="Could not export"):
        export_dataset(headerless, "dbf", extra_args={}, file_handle=io.BytesIO())


# --- parse_command_line ---


def test_list_formats_flag():
    args, extra = parse_command_line(["--list-formats"])
    assert args.list_formats is True


def test_infile_only(sample_csv):
    args, extra = parse_command_line([str(sample_csv)])
    assert args.infiles == [sample_csv]
    assert args.outfile is None


def test_infile_and_outfile(sample_csv, tmp_path):
    out = tmp_path / "out.json"
    args, extra = parse_command_line([str(sample_csv), str(out)])
    assert args.infiles == [sample_csv]
    assert args.outfile == out


def test_format_flag(sample_csv):
    args, extra = parse_command_line(["-t", "json", str(sample_csv)])
    assert args.out_format == "json"


def test_extra_args_collected(sample_csv):
    args, extra = parse_command_line(["--skip-lines", "2", str(sample_csv)])
    assert extra["skip_lines"] == 2


def test_no_input_exits():
    with pytest.raises(SystemExit):
        parse_command_line([], stdin_isatty=True)


def test_nonexistent_file_exits():
    with pytest.raises(SystemExit):
        parse_command_line(["/no/such/file.csv"])


def test_invalid_format_exits(sample_csv):
    with pytest.raises(SystemExit):
        parse_command_line(["-t", "bogus", str(sample_csv)])


def test_list_formats_with_file_exits(sample_csv):
    with pytest.raises(SystemExit):
        parse_command_line(["--list-formats", str(sample_csv)])


def test_from_flag_sets_in_format(sample_csv):
    args, _ = parse_command_line(["--from", "csv", str(sample_csv)])
    assert args.in_format == "csv"


def test_to_flag_sets_out_format(sample_csv):
    args, _ = parse_command_line(["--to", "json", str(sample_csv)])
    assert args.out_format == "json"


@pytest.mark.parametrize("flag", ["--list", "--in-format", "--format"])
def test_dropped_spellings_rejected(sample_csv, flag):
    """The old long forms fail loud, never silently change meaning."""
    with pytest.raises(SystemExit):
        parse_command_line([flag, "csv", str(sample_csv)])


def test_bare_l_requires_input_file():
    """-l is now --list-sheets, so it needs an input file."""
    with pytest.raises(SystemExit):
        parse_command_line(["-l"], stdin_isatty=True)


def test_delimiter_extra_arg(sample_csv):
    args, extra = parse_command_line(["-d", ";", str(sample_csv)])
    assert extra["delimiter"] == ";"


@pytest.mark.parametrize(
    ("flag", "key"),
    [("-H", "headers"), ("--no-xlsx-optimize", "read_only")],
)
def test_store_const_flags(sample_csv, flag, key):
    """store_const flags should be absent by default, False when set."""
    _, extra_default = parse_command_line([str(sample_csv)])
    assert key not in extra_default
    _, extra_set = parse_command_line([flag, str(sample_csv)])
    assert extra_set[key] is False


# --- build_argument_parser ---


def test_returns_parser():
    parser = build_argument_parser()
    assert isinstance(parser, type(build_argument_parser()))


def test_version_flag(capsys):
    parser = build_argument_parser()
    with pytest.raises(SystemExit, match="0"):
        parser.parse_args(["--version"])


# --- load_dataset_stdin ---


@pytest.mark.parametrize("fmt", ["csv", "json", "xlsx"])
def test_auto_detect(sample_data, fmt):
    raw = sample_data.export(fmt)
    if isinstance(raw, str):
        raw = raw.encode()
    ds = load_dataset_stdin(stdin=io.BytesIO(raw))
    assert len(ds) == 2
    assert ds.headers is not None
    assert "name" in ds.headers


def test_explicit_format():
    csv_bytes = b"name,age\nAlice,30\n"
    ds = load_dataset_stdin(in_format="csv", stdin=io.BytesIO(csv_bytes))
    assert len(ds) == 1


def test_extra_args_passed():
    csv_bytes = b"# comment\nname,age\nAlice,30\n"
    ds = load_dataset_stdin(
        in_format="csv",
        extra_args={"skip_lines": 1},
        stdin=io.BytesIO(csv_bytes),
    )
    assert len(ds) == 1
    assert ds.headers == ["name", "age"]


def test_load_dataset_empty_stdin_raises():
    with pytest.raises(TublubError, match="No data received"):
        load_dataset_stdin(stdin=io.BytesIO(b""))


def test_single_column_heuristic():
    """Single-column data on stdin should be detected as TSV via heuristic."""
    ds = load_dataset_stdin(stdin=io.BytesIO(b"name\nAlice\nBob\n"))
    assert len(ds) == 2
    assert ds.headers == ["name"]


def test_undetectable_format_raises():
    with pytest.raises(TublubError, match=r"Unable to detect.*-f"):
        load_dataset_stdin(stdin=io.BytesIO(b"???"))


# --- parse_command_line stdin ---


def test_dash_sets_stdin_flag():
    args, _ = parse_command_line(["-", "-t", "json"], stdin_isatty=True)
    assert args.stdin is True
    assert args.infiles == []


def test_implicit_stdin_when_piped():
    args, _ = parse_command_line(["-t", "json"], stdin_isatty=False)
    assert args.stdin is True


def test_no_implicit_stdin_on_tty():
    """An interactive TTY with no input is a usage error, not stdin."""
    with pytest.raises(SystemExit):
        parse_command_line(["-t", "json"], stdin_isatty=True)


def test_in_format_flag():
    args, _ = parse_command_line(["-f", "csv", "-t", "json"], stdin_isatty=False)
    assert args.in_format == "csv"


def test_invalid_in_format_exits():
    with pytest.raises(SystemExit):
        parse_command_line(["-f", "bogus", "-t", "json"], stdin_isatty=False)


def test_in_format_with_file(sample_csv):
    args, _ = parse_command_line(["-f", "csv", str(sample_csv)])
    assert args.in_format == "csv"
    assert args.stdin is False


# --- _unique_titles ---


def test_distinct_titles():
    entries = [("a", "d_a"), ("b", "d_b"), ("c", "d_c")]
    assert _unique_titles(entries) == ["a", "b", "c"]


def test_collision_uses_qualified(capsys):
    entries = [("sales", "d1_sales"), ("sales", "d2_sales")]
    assert _unique_titles(entries) == ["d1_sales", "d2_sales"]
    assert "disambiguated" in capsys.readouterr().err


def test_triple_collision_uses_qualified():
    entries = [("x", "a_x"), ("x", "b_x"), ("x", "c_x")]
    assert _unique_titles(entries) == ["a_x", "b_x", "c_x"]


def test_mixed_collisions():
    # Clashes are counted per preferred title: "users" keeps its own name
    # even though the other three entries fall back to qualified forms.
    entries = [
        ("sales", "a_sales"),
        ("users", "d_users"),
        ("sales", "b_sales"),
        ("sales", "c_sales"),
    ]
    assert _unique_titles(entries) == ["a_sales", "users", "b_sales", "c_sales"]


def test_qualified_collision_falls_back_to_numeric_suffix():
    # Both entries qualify to the same name (same parent dir name, or
    # two same-titled sheets in one workbook) → the _2 suffix kicks in.
    entries = [("x", "data_x"), ("x", "data_x")]
    assert _unique_titles(entries) == ["data_x", "data_x_2"]


def test_unqualifiable_entry_falls_back_to_numeric_suffix(capsys):
    # A path with no parent name qualifies to its own stem.
    entries = [("Sales", "Sales"), ("Sales", "dir_Sales")]
    assert _unique_titles(entries) == ["Sales", "dir_Sales"]
    assert "disambiguated" in capsys.readouterr().err


def test_no_collision_no_note(capsys):
    _unique_titles([("a", "d_a"), ("b", "d_b")])
    assert capsys.readouterr().err == ""


def test_unique_titles_empty():
    assert _unique_titles([]) == []


def test_long_title_truncated_to_limit(capsys):
    long = "a" * 40
    titles = _unique_titles([(long, long)])
    assert titles == ["a" * 31]
    assert "disambiguated" in capsys.readouterr().err


def test_long_shared_prefix_stays_unique():
    # Two distinct titles sharing a >31-char prefix clamp to the same 31
    # chars, so the _2 suffix kicks in with the base trimmed to fit.
    prefix = "x" * 40
    entries = [(f"{prefix}A", f"{prefix}A"), (f"{prefix}B", f"{prefix}B")]
    titles = _unique_titles(entries)
    assert all(len(t) <= 31 for t in titles)
    assert titles == ["x" * 31, "x" * 29 + "_2"]


# --- build_databook ---


def test_two_inputs(sample_csv, sample_json):
    book = build_databook([sample_csv, sample_json], extra_args={})
    assert book.size == 2
    titles = [s.title for s in book.sheets()]
    # Both fixtures share stem "data" and parent dir, so disambiguation
    # falls back to a numeric suffix on the parent-qualified base.
    assert len(set(titles)) == 2
    assert all("data" in t for t in titles)


def test_sheet_data_preserved(sample_csv, sample_json):
    book = build_databook([sample_csv, sample_json], extra_args={})
    sheets = book.sheets()
    assert sheets[0].headers == ["name", "age", "city"]
    assert len(sheets[0]) == 2
    assert len(sheets[1]) == 2


def test_distinct_stems(tmp_path):
    a = tmp_path / "sales.csv"
    a.write_text("name,age\nAlice,30\n")
    b = tmp_path / "users.csv"
    b.write_text("name,age\nBob,25\n")
    book = build_databook([a, b], extra_args={})
    assert [s.title for s in book.sheets()] == ["sales", "users"]


# --- save_databook_file ---


def test_save_xlsx(sample_csv, sample_json, tmp_path):
    out = tmp_path / "book.xlsx"
    book = build_databook([sample_csv, sample_json], extra_args={})
    save_databook_file(book, out, extra_args={})
    assert out.exists()
    assert out.stat().st_size > 0
    # Verify it's a real XLSX with two sheets
    loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
    assert loaded.size == 2
    titles = [s.title for s in loaded.sheets()]
    assert len(set(titles)) == 2
    assert all("data" in t for t in titles)


def test_save_unsupported_format_raises(sample_csv, tmp_path):
    """CSV doesn't support Databook export — should raise TublubError."""
    out = tmp_path / "book.csv"
    book = build_databook([sample_csv, sample_csv], extra_args={})
    with pytest.raises(TublubError, match="multi-sheet"):
        save_databook_file(book, out, extra_args={})
    assert not out.exists()


def test_save_databook_unknown_format_raises(sample_csv, tmp_path):
    out = tmp_path / "book.xyz"
    book = build_databook([sample_csv, sample_csv], extra_args={})
    with pytest.raises(TublubError, match="Unable to detect"):
        save_databook_file(book, out, extra_args={})


def test_force_format_overrides_extension(sample_csv, tmp_path):
    out = tmp_path / "book.bin"
    book = build_databook([sample_csv, sample_csv], extra_args={})
    save_databook_file(book, out, extra_args={}, force_format="xlsx")
    loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
    assert loaded.size == 2


# --- MultiSheetUnsupportedError ---


def test_export_raises_subclass_carrying_the_format(sample_csv):
    """The default-mode fallback needs the format that was attempted."""
    book = build_databook([sample_csv, sample_csv], extra_args={})
    with pytest.raises(MultiSheetUnsupportedError) as excinfo:
        export_databook(book, "csv", {}, file_handle=io.StringIO())
    assert issubclass(MultiSheetUnsupportedError, TublubError)
    assert excinfo.value.target_format == "csv"
    assert "does not support multi-sheet output" in str(excinfo.value)


def test_hint_still_appended(sample_csv):
    book = build_databook([sample_csv, sample_csv], extra_args={})
    with pytest.raises(MultiSheetUnsupportedError) as excinfo:
        export_databook(
            book, "csv", {}, file_handle=io.StringIO(), hint="pick one sheet"
        )
    assert str(excinfo.value).endswith("; pick one sheet")


def test_binary_to_tty_is_not_the_fallback_signal():
    """Only the unsupported-format failure may trigger a fallback."""

    class TTYStdout(io.TextIOWrapper):
        def isatty(self):
            return True

    with pytest.raises(TublubError) as excinfo:
        _default_export_handle("xlsx", stdout=TTYStdout(io.BytesIO()))
    assert not isinstance(excinfo.value, MultiSheetUnsupportedError)


# --- export failures ---


def test_cli_failed_save_keeps_existing_file(sample_csv, existing_out):
    existing_args = ["-H", "-t", "dbf", "-y", "-o", str(existing_out)]
    with pytest.raises(SystemExit) as excinfo:
        cli([*existing_args, str(sample_csv)])
    assert "dbf" in str(excinfo.value)
    assert existing_out.read_text() == "sentinel"


def test_cli_failed_export_to_stdout_exits_cleanly(sample_csv):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-H", "-t", "dbf", str(sample_csv)])
    assert "Could not export" in str(excinfo.value)


# --- load_databook_file ---


def test_load_databook_multi_sheet_xlsx_returns_book(multi_sheet_xlsx):
    book = load_databook_file(multi_sheet_xlsx, extra_args={})
    assert book is not None
    assert book.size == 2
    assert [s.title for s in book.sheets()] == ["people", "cities"]


def test_csv_returns_none(sample_csv):
    assert load_databook_file(sample_csv, extra_args={}) is None


def test_tsv_returns_none(sample_tsv):
    assert load_databook_file(sample_tsv, extra_args={}) is None


def test_records_json_returns_none(sample_json):
    """JSON of records (single-Dataset shape) is not a Databook."""
    assert load_databook_file(sample_json, extra_args={}) is None


def test_records_yaml_returns_none(sample_yaml):
    """YAML of records (single-Dataset shape) is not a Databook."""
    assert load_databook_file(sample_yaml, extra_args={}) is None


def test_malformed_xlsx_propagates_error(tmp_path):
    """Real load errors must propagate, not be swallowed as None."""
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not really an xlsx file")
    # Underlying error comes from openpyxl/zipfile; we don't pin the
    # exact type, only that it's not silently None and not TublubError.
    with pytest.raises(Exception, match=r".+") as exc_info:
        load_databook_file(bad, extra_args={})
    assert not isinstance(exc_info.value, TublubError)


def test_in_format_override(multi_sheet_xlsx):
    book = load_databook_file(multi_sheet_xlsx, extra_args={}, in_format="xlsx")
    assert book is not None
    assert book.size == 2


def test_unknown_format_raises(tmp_path):
    bad = tmp_path / "data.xyz"
    bad.write_text("nothing")
    with pytest.raises(TublubError, match="Unable to detect"):
        load_databook_file(bad, extra_args={})


def test_broken_json_syntax_propagates(tmp_path):
    """The (UnsupportedFormat, KeyError, TypeError) catch must not swallow
    a JSONDecodeError from a syntactically broken JSON file."""
    bad = tmp_path / "broken.json"
    bad.write_bytes(b'{"foo":')
    with pytest.raises(Exception, match=r".+") as exc_info:
        try_load_file(bad, extra_args={})
    assert not isinstance(exc_info.value, TublubError)
    assert isinstance(exc_info.value, ValueError)  # JSONDecodeError


def test_tablib_hostile_json_shape_propagates(tmp_path):
    """JSON valid as syntax but not a Dataset or Databook shape must
    surface as an error (UnsupportedFormat), not silently fall back."""
    bad = tmp_path / "weird.json"
    bad.write_bytes(b'{"random": "object"}')
    with pytest.raises(tablib.UnsupportedFormat):
        try_load_file(bad, extra_args={})


def test_wrong_extension_warns_once(tmp_path, capsys):
    """A wrong-extension input warns about the extension/content mismatch
    once, not once per attempted shape."""
    p = tmp_path / "data.xls"
    p.write_text("name,age\nAlice,30\nBob,25\n")
    loaded = try_load_file(p, extra_args={})
    assert isinstance(loaded, tablib.Dataset)
    err = capsys.readouterr().err
    assert err.count("Extension suggests xls but content detected as csv") == 1


# --- load_databook_stdin ---


def test_multi_sheet_xlsx_from_stdin(multi_sheet_xlsx):
    book = load_databook_stdin(stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()))
    assert book is not None
    assert book.size == 2


def test_csv_from_stdin_returns_none():
    stdin = io.BytesIO(b"name,age\nAlice,30\nBob,25\n")
    assert load_databook_stdin(stdin=stdin) is None


def test_load_databook_empty_stdin_raises():
    with pytest.raises(TublubError, match="No data"):
        load_databook_stdin(stdin=io.BytesIO(b""))


# --- try_load_stdin ---


def test_try_load_multi_sheet_xlsx_returns_book(multi_sheet_xlsx):
    loaded = try_load_stdin(stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()))
    assert isinstance(loaded, tablib.Databook)
    assert loaded.size == 2


def test_csv_returns_dataset():
    loaded = try_load_stdin(stdin=io.BytesIO(b"name,age\nAlice,30\n"))
    assert isinstance(loaded, tablib.Dataset)
    assert "Alice" in str(loaded)


def test_try_load_empty_stdin_raises():
    with pytest.raises(TublubError, match="No data received"):
        try_load_stdin(stdin=io.BytesIO(b""))


# --- non-UTF-8 input ---

LATIN1_CSV = b"id,name\n1,R\xe4ksm\xf6rg\xe5s\n"  # latin-1 "Räksmörgås"


def test_non_utf8_stdin_raises():
    with pytest.raises(TublubError, match="UTF-8"):
        try_load_stdin(in_format="csv", stdin=io.BytesIO(LATIN1_CSV))


def test_non_utf8_dataset_stdin_raises():
    with pytest.raises(TublubError, match="UTF-8"):
        load_dataset_stdin(in_format="csv", stdin=io.BytesIO(LATIN1_CSV))


def test_non_utf8_file_raises(tmp_path):
    p = tmp_path / "latin.csv"
    p.write_bytes(LATIN1_CSV)
    with pytest.raises(TublubError, match=r"latin\.csv"):
        try_load_file(p, extra_args={})


def test_cli_non_utf8_stdin_exits():
    with pytest.raises(SystemExit) as excinfo:
        cli(["-f", "csv", "-"], stdin=io.BytesIO(LATIN1_CSV))
    assert "UTF-8" in str(excinfo.value)


# --- load options on a multi-sheet input ---


def test_skip_lines_multi_sheet_file_errors(multi_sheet_xlsx):
    with pytest.raises(TublubError, match="--skip-lines"):
        try_load_file(multi_sheet_xlsx, extra_args={"skip_lines": 1})


def test_skip_lines_multi_sheet_book_helper_errors(multi_sheet_xlsx):
    with pytest.raises(TublubError, match="--skip-lines"):
        load_databook_file(multi_sheet_xlsx, extra_args={"skip_lines": 1})


def test_skip_lines_multi_sheet_stdin_errors(multi_sheet_xlsx):
    stdin = io.BytesIO(multi_sheet_xlsx.read_bytes())
    with pytest.raises(TublubError, match="--skip-lines"):
        try_load_stdin(extra_args={"skip_lines": 1}, stdin=stdin)


def test_skip_lines_single_sheet_still_loads(one_sheet_xlsx):
    loaded = try_load_file(one_sheet_xlsx, extra_args={"skip_lines": 1})
    assert isinstance(loaded, tablib.Dataset)
    assert len(loaded) == 1


def test_skip_lines_csv_unaffected(sample_csv):
    loaded = try_load_file(sample_csv, extra_args={"skip_lines": 1})
    assert isinstance(loaded, tablib.Dataset)
    assert len(loaded) == 1


def test_cli_list_sheets_with_skip_lines_exits(multi_sheet_xlsx):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-l", "--skip-lines", "1", str(multi_sheet_xlsx)])
    assert "--skip-lines" in str(excinfo.value)


def test_cli_sheet_selection_with_skip_lines_exits(multi_sheet_xlsx):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "1", "--skip-lines", "1", str(multi_sheet_xlsx)])
    assert "--skip-lines" in str(excinfo.value)


# --- parse_command_line: multi-input mode ---


def test_o_flag_with_two_inputs(sample_csv, sample_json, tmp_path):
    out = tmp_path / "book.xlsx"
    args, _ = parse_command_line(["-o", str(out), str(sample_csv), str(sample_json)])
    assert args.infiles == [sample_csv, sample_json]
    assert args.outfile == out


def test_o_flag_with_single_input(sample_csv, tmp_path):
    """Single input under -o populates args.infiles (single-file path)."""
    out = tmp_path / "out.json"
    args, _ = parse_command_line(["-o", str(out), str(sample_csv)])
    assert args.infiles == [sample_csv]
    assert args.outfile == out


def test_three_positionals_without_o_exits(sample_csv, tmp_path):
    out = tmp_path / "out.json"
    with pytest.raises(SystemExit):
        parse_command_line([str(sample_csv), str(sample_csv), str(out)])


def test_stdin_rejected_in_multi_input(sample_csv, tmp_path):
    out = tmp_path / "book.xlsx"
    with pytest.raises(SystemExit):
        parse_command_line(["-o", str(out), "-", str(sample_csv)])


def test_o_with_no_inputs_and_tty_exits(tmp_path):
    out = tmp_path / "out.json"
    with pytest.raises(SystemExit):
        parse_command_line(["-o", str(out)], stdin_isatty=True)


def test_nonexistent_input_in_multi_exits(sample_csv, tmp_path):
    out = tmp_path / "book.xlsx"
    with pytest.raises(SystemExit):
        parse_command_line(["-o", str(out), str(sample_csv), "/no/such/file.csv"])


# --- cli() integration: multi-input → Databook ---


def test_multi_input_to_xlsx(sample_csv, sample_json, tmp_path):
    out = tmp_path / "book.xlsx"
    rc = cli(["-o", str(out), str(sample_csv), str(sample_json)])
    assert rc == 0
    loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
    assert loaded.size == 2


def test_unsupported_output_exits(sample_csv, tmp_path):
    out = tmp_path / "book.csv"
    with pytest.raises(SystemExit):
        cli(["-o", str(out), str(sample_csv), str(sample_csv)])


# --- multi-input sheet expansion ---


def _titles(*paths):
    return [s.title for s in build_databook(list(paths), extra_args={}).sheets()]


def test_book_sheets_expand_alongside_dataset(multi_sheet_xlsx, sample_csv):
    assert _titles(multi_sheet_xlsx, sample_csv) == ["people", "cities", "data"]


def test_no_note_when_titles_survive(multi_sheet_xlsx, sample_csv, capsys):
    _titles(multi_sheet_xlsx, sample_csv)
    assert capsys.readouterr().err == ""


def test_one_sheet_book_keeps_its_title(one_sheet_xlsx, sample_csv):
    assert _titles(one_sheet_xlsx, sample_csv) == ["people", "data"]


def test_clash_across_inputs_qualifies_by_stem(multi_sheet_xlsx, capsys):
    assert _titles(multi_sheet_xlsx, multi_sheet_xlsx) == [
        "book__people",
        "book__cities",
        "book__people_2",
        "book__cities_2",
    ]
    assert "disambiguated" in capsys.readouterr().err


def test_clash_within_one_input(dup_title_json):
    assert _titles(dup_title_json) == ["dup__Users", "Costs", "dup__Users_2"]


def test_dataset_title_clashing_with_sheet_title(multi_sheet_xlsx, tmp_path):
    # A file stem clashing with a sheet title qualifies by parent
    # directory, the sheet by its workbook stem.
    subdir = tmp_path / "hr"
    subdir.mkdir()
    people = subdir / "people.csv"
    people.write_text("name,age\nCarol,41\n")
    assert _titles(multi_sheet_xlsx, people) == [
        "book__people",
        "cities",
        "hr_people",
    ]


def test_long_clashing_titles_clamped(tmp_path):
    rows = [{"a": 1}]
    title = "T" * 25
    path = tmp_path / f"{'s' * 20}.json"
    path.write_text(
        json.dumps([{"title": title, "data": rows}, {"title": title, "data": rows}])
    )
    titles = _titles(path)
    assert all(len(t) <= 31 for t in titles)
    assert len(set(titles)) == 2


def test_untitled_sheet_expands(empty_title_json):
    assert _titles(empty_title_json) == ["", "named"]


def test_empty_workbook_contributes_nothing(empty_workbook, sample_csv):
    assert _titles(empty_workbook, sample_csv) == ["data"]


def test_all_inputs_empty_exits(empty_workbook, tmp_path):
    second = tmp_path / "other.json"
    second.write_text("[]")
    out = tmp_path / "out.xlsx"
    with pytest.raises(SystemExit):
        cli(["-o", str(out), str(empty_workbook), str(second)])


def test_cli_round_trip(multi_sheet_xlsx, sample_csv, tmp_path):
    out = tmp_path / "merged.xlsx"
    assert cli(["-o", str(out), str(multi_sheet_xlsx), str(sample_csv)]) == 0
    loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
    assert [s.title for s in loaded.sheets()] == ["people", "cities", "data"]


def test_sheet_flag_rejected_with_two_inputs(multi_sheet_xlsx, sample_csv):
    with pytest.raises(SystemExit):
        parse_command_line(
            ["-o", "out.xlsx", "-s", "0", str(multi_sheet_xlsx), str(sample_csv)]
        )


def test_all_sheets_rejected_with_two_inputs(multi_sheet_xlsx, sample_csv):
    with pytest.raises(SystemExit):
        parse_command_line(
            [
                "-o",
                "out.xlsx",
                "--all-sheets",
                str(multi_sheet_xlsx),
                str(sample_csv),
            ]
        )


# --- --list-sheets ---


def test_argparse_flag(sample_csv):
    args, _ = parse_command_line(["--list-sheets", str(sample_csv)])
    assert args.list_sheets is True


def test_xlsx_lists_all_sheets(multi_sheet_xlsx, capsys):
    rc = cli(["--list-sheets", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0] == "[0] people  2 rows x 2 cols"
    assert lines[1] == "[1] cities  2 rows x 2 cols"


def test_one_sheet_xlsx_keeps_index(one_sheet_xlsx, capsys):
    """A one-sheet workbook still has sheet structure, so [0] is shown."""
    rc = cli(["--list-sheets", str(one_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "[0] people  2 rows x 2 cols\n"


def test_csv_falls_back_to_dataset(sample_csv, capsys):
    """No sheet structure: one bare line, no index or title."""
    rc = cli(["--list-sheets", str(sample_csv)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "2 rows x 3 cols\n"


def test_records_json_falls_back_to_dataset(sample_json, capsys):
    """Records-shaped JSON has no sheet structure: one bare line."""
    rc = cli(["--list-sheets", str(sample_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "2 rows x 3 cols\n"


def test_empty_workbook_prints_nothing(empty_workbook, capsys):
    rc = cli(["--list-sheets", str(empty_workbook)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == ""


def test_stdin_lists_all_sheets(multi_sheet_xlsx, capsys):
    """Piped input lists exactly as the same file passed by name does."""
    rc = cli(["--list-sheets", "-"], stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()))
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "[0] people  2 rows x 2 cols\n[1] cities  2 rows x 2 cols\n"


def test_stdin_csv_falls_back_to_dataset(capsys):
    rc = cli(["--list-sheets", "-"], stdin=io.BytesIO(b"name,age\nAlice,30\n"))
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "1 rows x 2 cols\n"


def test_unknown_format_exits(tmp_path):
    bogus = tmp_path / "mystery.xyz"
    bogus.write_bytes(b"\x00\x01\x02not-a-known-format")
    with pytest.raises(SystemExit):
        cli(["--list-sheets", str(bogus)])


def test_headerless_input_reports_columns(sample_csv, capsys):
    rc = cli(["--list-sheets", "-H", str(sample_csv)])
    assert rc == 0
    assert capsys.readouterr().out == "3 rows x 3 cols\n"


def test_combined_with_output_rejected(sample_csv, tmp_path):
    out = tmp_path / "out.xlsx"
    with pytest.raises(SystemExit):
        parse_command_line(["--list-sheets", "-o", str(out), str(sample_csv)])


def test_combined_with_format_rejected(sample_csv):
    with pytest.raises(SystemExit):
        parse_command_line(["--list-sheets", "-t", "csv", str(sample_csv)])


def test_list_sheets_combined_with_list_formats_rejected(sample_csv):
    with pytest.raises(SystemExit):
        parse_command_line(["--list-sheets", "--list-formats", str(sample_csv)])


def test_list_sheets_no_input_rejected():
    with pytest.raises(SystemExit):
        parse_command_line(["--list-sheets"], stdin_isatty=True)


def test_two_inputs_rejected(sample_csv, sample_json):
    with pytest.raises(SystemExit):
        parse_command_line(["--list-sheets", str(sample_csv), str(sample_json)])


# --- -s/--sheet ---


# argparse level: token cooking and rejections


def test_occurrences_append(multi_sheet_xlsx):
    args, _ = parse_command_line(["-s", "Users", "-s", "cities", str(multi_sheet_xlsx)])
    assert args.sheets == ["Users", "cities"]


def test_comma_split_when_all_ints(multi_sheet_xlsx):
    args, _ = parse_command_line(["-s", " 0 , 2 ", str(multi_sheet_xlsx)])
    assert args.sheets == ["0", "2"]


def test_mixed_comma_stays_literal(multi_sheet_xlsx):
    args, _ = parse_command_line(["-s", "0,Users", str(multi_sheet_xlsx)])
    assert args.sheets == ["0,Users"]


def test_title_with_comma_stays_whole(multi_sheet_xlsx):
    args, _ = parse_command_line(["-s", "Revenue, EMEA", str(multi_sheet_xlsx)])
    assert args.sheets == ["Revenue, EMEA"]


@pytest.mark.parametrize("selector", ["", ",", "0,", " , "])
def test_empty_selector_rejected(multi_sheet_xlsx, selector):
    with pytest.raises(SystemExit):
        parse_command_line(["-s", selector, str(multi_sheet_xlsx)])


# ranges


@pytest.mark.parametrize("selector", ["0-4", "2-"])
def test_bare_range_kept_whole(multi_sheet_xlsx, selector):
    args, _ = parse_command_line(["-s", selector, str(multi_sheet_xlsx)])
    assert args.sheets == [selector]


def test_range_in_comma_list_splits(multi_sheet_xlsx):
    args, _ = parse_command_line(["-s", "0,2-4", str(multi_sheet_xlsx)])
    assert args.sheets == ["0", "2-4"]


def test_all_range_comma_list_splits(multi_sheet_xlsx):
    args, _ = parse_command_line(["-s", "0-1,2-", str(multi_sheet_xlsx)])
    assert args.sheets == ["0-1", "2-"]


@pytest.mark.parametrize("selector", ["0 - 4", "0-4-6", "0-+4", "-"])
def test_non_range_shapes_stay_literal(multi_sheet_xlsx, selector):
    args, _ = parse_command_line(["-s", selector, str(multi_sheet_xlsx)])
    assert args.sheets == [selector]


def test_range_mixed_with_title_stays_literal(multi_sheet_xlsx):
    args, _ = parse_command_line(["-s", "0-2,Users", str(multi_sheet_xlsx)])
    assert args.sheets == ["0-2,Users"]


def test_decreasing_range_rejected(multi_sheet_xlsx, capsys):
    with pytest.raises(SystemExit):
        parse_command_line(["-s", "4-2", str(multi_sheet_xlsx)])
    assert "invalid decreasing sheet range 4-2" in capsys.readouterr().err


def test_decreasing_range_in_comma_list_rejected(multi_sheet_xlsx, capsys):
    with pytest.raises(SystemExit):
        parse_command_line(["-s", "0,4-2", str(multi_sheet_xlsx)])
    assert "invalid decreasing sheet range 4-2" in capsys.readouterr().err


def test_combined_with_all_sheets_rejected(multi_sheet_xlsx):
    with pytest.raises(SystemExit):
        parse_command_line(["-s", "0", "--all-sheets", str(multi_sheet_xlsx)])


def test_sheet_combined_with_list_sheets_rejected(multi_sheet_xlsx):
    with pytest.raises(SystemExit):
        parse_command_line(["-s", "0", "--list-sheets", str(multi_sheet_xlsx)])


def test_sheet_combined_with_list_formats_rejected():
    with pytest.raises(SystemExit):
        parse_command_line(["-s", "0", "--list-formats"])


def test_stdin_explicit_accepted():
    args, _ = parse_command_line(["-s", "0", "-"])
    assert args.stdin is True
    assert args.infiles == []


def test_stdin_implicit_accepted():
    args, _ = parse_command_line(["-s", "0"], stdin_isatty=False)
    assert args.stdin is True


def test_sheet_no_input_rejected():
    with pytest.raises(SystemExit):
        parse_command_line(["-s", "0"], stdin_isatty=True)


def test_sheet_multiple_inputs_rejected(sample_csv, sample_json, tmp_path):
    out = tmp_path / "out.xlsx"
    with pytest.raises(SystemExit):
        parse_command_line(
            ["-s", "0", "-o", str(out), str(sample_csv), str(sample_json)]
        )


# cli level: resolution


def test_pick_by_index(multi_sheet_xlsx, capsys):
    rc = cli(["-s", "1", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Stockholm" in out
    assert "Alice" not in out
    assert "===" not in out


def test_pick_by_title(multi_sheet_xlsx, capsys):
    rc = cli(["-s", "people", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Alice" in out
    assert "===" not in out


def test_pick_by_case_insensitive_title(multi_sheet_xlsx, capsys):
    rc = cli(["-s", "PEOPLE", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Alice" in out


def test_year_index_out_of_range_hints_name(year_title_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "2024", str(year_title_json)])
    msg = str(excinfo.value)
    assert "sheet index 2024 out of range (0-0)" in msg
    assert "\nfor the sheet titled '2024' use --sheet name:2024" in msg


def test_name_prefix_forces_title(year_title_json, capsys):
    rc = cli(["-s", "name:2024", str(year_title_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Jan" in out


def test_out_of_range_without_matching_title(multi_sheet_xlsx):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "9", str(multi_sheet_xlsx)])
    msg = str(excinfo.value)
    assert "sheet index 9 out of range (0-1)" in msg
    assert "name:" not in msg


def test_doubled_name_prefix_escapes_literal(tmp_path, capsys):
    book = [{"title": "name:2024", "data": [{"month": "Jan"}]}]
    p = tmp_path / "odd.json"
    p.write_text(json.dumps(book))
    rc = cli(["-s", "name:name:2024", str(p)])
    assert rc == 0
    assert "Jan" in capsys.readouterr().out


def test_duplicate_titles_ambiguous(dup_title_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "Users", str(dup_title_json)])
    msg = str(excinfo.value)
    assert "ambiguous" in msg
    assert "[0]" in msg
    assert "[2]" in msg


def test_case_insensitive_ambiguous(case_dup_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "Users", str(case_dup_json)])
    assert "ambiguous" in str(excinfo.value)


def test_exact_match_beats_case_insensitive(case_dup_json, capsys):
    rc = cli(["-s", "users", str(case_dup_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Alice" in out
    assert "Bob" not in out


def test_unknown_title_lists_titles(multi_sheet_xlsx):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "nope", str(multi_sheet_xlsx)])
    msg = str(excinfo.value)
    assert "no sheet titled 'nope'" in msg
    assert "'people'" in msg
    assert "'cities'" in msg
    assert "repeat --sheet" not in msg
    assert "--list-sheets" not in msg


def test_many_titles_truncated_with_list_hint(many_sheets_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "nope", str(many_sheets_json)])
    msg = str(excinfo.value)
    assert "'sheet00'" in msg
    assert "'sheet09'" in msg
    assert "'sheet10'" not in msg
    assert "and 2 more, run --list-sheets to see them all" in msg


def test_untitled_sheets_say_select_by_index(untitled_sheets_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "nope", str(untitled_sheets_json)])
    msg = str(excinfo.value)
    assert "this input's sheets have no titles, select by index" in msg
    assert "available titles" not in msg


def test_comma_miss_adds_repeat_hint(multi_sheet_xlsx):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "0,people", str(multi_sheet_xlsx)])
    msg = str(excinfo.value)
    assert "no sheet titled '0,people'" in msg
    assert "\nrepeat --sheet to combine names with indices or ranges" in msg


def test_sheet_empty_workbook_errors(empty_workbook):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "0", str(empty_workbook)])
    assert "workbook has no sheets" in str(excinfo.value)


def test_empty_title_selectable_by_index_only(empty_title_json, capsys):
    rc = cli(["-s", "0", str(empty_title_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Alice" in out


def test_empty_title_skipped_in_title_match(empty_title_json, capsys):
    rc = cli(["-s", "named", str(empty_title_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Bob" in out


@pytest.mark.parametrize("fixture", ["sample_csv", "sample_json"])
def test_no_sheet_structure_rejected(fixture, request):
    path = request.getfixturevalue(fixture)
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "0", str(path)])
    assert "input has no sheet structure" in str(excinfo.value)


def test_one_sheet_workbook_selectable_by_index(one_sheet_xlsx, capsys):
    rc = cli(["-s", "0", str(one_sheet_xlsx)])
    assert rc == 0
    assert "Alice" in capsys.readouterr().out


def test_one_sheet_workbook_selectable_by_title(one_sheet_xlsx, capsys):
    rc = cli(["-s", "people", str(one_sheet_xlsx)])
    assert rc == 0
    assert "Alice" in capsys.readouterr().out


# ranges


def test_range_out_of_range_errors(multi_sheet_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "0-4", str(multi_sheet_json)])
    msg = str(excinfo.value)
    assert "sheet range 0-4 out of range (0-2)" in msg
    assert "name:" not in msg


def test_open_range_past_last_errors(multi_sheet_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "3-", str(multi_sheet_json)])
    assert "sheet range 3- out of range (0-2)" in str(excinfo.value)


def test_range_out_of_range_hints_name(range_title_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "1-5", str(range_title_json)])
    msg = str(excinfo.value)
    assert "sheet range 1-5 out of range (0-0)" in msg
    assert "\nfor the sheet titled '1-5' use --sheet name:1-5" in msg


def test_name_prefix_selects_range_titled_sheet(range_title_json, capsys):
    rc = cli(["-s", "name:1-5", str(range_title_json)])
    assert rc == 0
    assert "Jan" in capsys.readouterr().out


def test_range_on_single_sheet_book(year_title_json, capsys):
    rc = cli(["-s", "0-0", str(year_title_json)])
    assert rc == 0
    assert "Jan" in capsys.readouterr().out


def test_negative_index_still_errors_out_of_range(multi_sheet_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "-1", str(multi_sheet_json)])
    assert "sheet index -1 out of range (0-2)" in str(excinfo.value)


@pytest.mark.parametrize("selector", ["-", "0-4-6"])
def test_dashed_non_range_is_title_miss(multi_sheet_json, selector):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", selector, str(multi_sheet_json)])
    assert f"no sheet titled '{selector}'" in str(excinfo.value)


def test_range_comma_title_miss_hints_repeat(multi_sheet_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "2-4,Users", str(multi_sheet_json)])
    msg = str(excinfo.value)
    assert "no sheet titled '2-4,Users'" in msg
    assert "\nrepeat --sheet to combine names with indices or ranges" in msg


# cli level: rendering


def test_multi_select_print_layout(multi_sheet_json, capsys):
    rc = cli(["-s", "0,2", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== people (2 rows) ===", "=== products (1 rows) ==="]
    assert "cities" not in out
    # exactly one blank line between sheets, none after the last
    assert "\n\n=== products (1 rows) ===\n" in out
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_selection_order_preserved(multi_sheet_json, capsys):
    rc = cli(["-s", "2,0", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.index("=== products") < out.index("=== people")


def test_duplicates_deduped(multi_sheet_json, capsys):
    rc = cli(["-s", "0,1,0", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]


def test_dedup_to_single_renders_plain(multi_sheet_json, capsys):
    rc = cli(["-s", "0,0", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "===" not in out
    assert "Alice" in out


# ranges


def test_closed_range_selects_inclusive_span(multi_sheet_json, capsys):
    rc = cli(["-s", "0-1", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]


def test_open_range_runs_to_last_sheet(multi_sheet_json, capsys):
    rc = cli(["-s", "1-", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== cities (2 rows) ===", "=== products (1 rows) ==="]


def test_range_to_single_sheet_renders_plain(multi_sheet_json, capsys):
    rc = cli(["-s", "1-1", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "===" not in out
    assert "Stockholm" in out


def test_range_mixed_with_index_keeps_order(multi_sheet_json, capsys):
    rc = cli(["-s", "2,0-1", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == [
        "=== products (1 rows) ===",
        "=== people (2 rows) ===",
        "=== cities (2 rows) ===",
    ]


def test_range_overlap_dedups(multi_sheet_json, capsys):
    rc = cli(["-s", "0-1,0", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]


def test_repeat_flag_mixes_title_and_index(multi_sheet_json, capsys):
    rc = cli(["-s", "people", "-s", "1", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]


def test_stdin_pick_by_title(multi_sheet_xlsx, capsys):
    rc = cli(["-s", "cities", "-"], stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Stockholm" in out
    assert "Alice" not in out
    assert "===" not in out


def test_stdin_multi_selection_prints_headings(multi_sheet_xlsx, capsys):
    rc = cli(["-s", "0,1", "-"], stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()))
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]


def test_single_select_save(multi_sheet_xlsx, tmp_path):
    out_file = tmp_path / "cities.csv"
    rc = cli(["-s", "cities", "-o", str(out_file), str(multi_sheet_xlsx)])
    assert rc == 0
    assert "Stockholm" in out_file.read_text()


def test_single_select_export(multi_sheet_xlsx, capsys):
    rc = cli(["-s", "0", "-t", "json", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    rows = json.loads(out)
    assert rows[0]["name"] == "Alice"


def test_multi_select_export_json(multi_sheet_json, capsys):
    rc = cli(["-s", "0,1", "-t", "json", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    book = json.loads(out)
    assert [sheet["title"] for sheet in book] == ["people", "cities"]


def test_multi_select_save_roundtrip(multi_sheet_json, tmp_path):
    out_file = tmp_path / "subset.xlsx"
    rc = cli(["-s", "2,0", "-o", str(out_file), str(multi_sheet_json)])
    assert rc == 0
    loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
    assert [s.title for s in loaded.sheets()] == ["products", "people"]


def test_multi_select_save_unsupported_hints_sheet(multi_sheet_json, tmp_path):
    out_file = tmp_path / "subset.csv"
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "0,1", "-o", str(out_file), str(multi_sheet_json)])
    msg = str(excinfo.value)
    assert "does not support multi-sheet output" in msg
    assert "pick one sheet with --sheet" in msg


def test_multi_select_export_unsupported_hints_sheet(multi_sheet_json):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-s", "0,1", "-t", "csv", str(multi_sheet_json)])
    msg = str(excinfo.value)
    assert "does not support multi-sheet output" in msg
    assert "pick one sheet with --sheet" in msg


def test_tablefmt_applies_to_multi_print(multi_sheet_json, capsys):
    rc = cli(["-s", "0,1", "--tablefmt", "grid", str(multi_sheet_json)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "+" in out


def test_tablefmt_applies_to_single_print(sample_csv, capsys):
    rc = cli(["--tablefmt", "grid", str(sample_csv)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "+---" in out


# --- --all-sheets ---


def test_print_all(multi_sheet_xlsx, capsys):
    rc = cli(["--all-sheets", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
    assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]


def test_save_roundtrip(multi_sheet_xlsx, tmp_path):
    out_file = tmp_path / "all.xlsx"
    rc = cli(["--all-sheets", "-o", str(out_file), str(multi_sheet_xlsx)])
    assert rc == 0
    loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
    assert loaded.size == 2


def test_save_unsupported_hints_sheet(multi_sheet_xlsx, tmp_path):
    out_file = tmp_path / "all.csv"
    with pytest.raises(SystemExit) as excinfo:
        cli(["--all-sheets", "-o", str(out_file), str(multi_sheet_xlsx)])
    msg = str(excinfo.value)
    assert "does not support multi-sheet output" in msg
    assert "pick one sheet with --sheet" in msg


def test_export_json(multi_sheet_xlsx, capsys):
    rc = cli(["--all-sheets", "-t", "json", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    book = json.loads(out)
    assert [sheet["title"] for sheet in book] == ["people", "cities"]


def test_identity_on_csv_print(sample_csv, capsys):
    rc = cli(["--all-sheets", str(sample_csv)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "===" not in out
    assert "Alice" in out


def test_identity_on_csv_export(sample_csv, capsys):
    rc = cli(["--all-sheets", "-t", "json", str(sample_csv)])
    out = capsys.readouterr().out
    assert rc == 0
    rows = json.loads(out)
    assert rows[0]["name"] == "Alice"


def test_one_sheet_workbook_single_render(one_sheet_xlsx, capsys):
    rc = cli(["--all-sheets", str(one_sheet_xlsx)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "===" not in out
    assert "Alice" in out


def test_all_sheets_empty_workbook_errors(empty_workbook):
    with pytest.raises(SystemExit) as excinfo:
        cli(["--all-sheets", str(empty_workbook)])
    assert "workbook has no sheets" in str(excinfo.value)


def test_all_sheets_combined_with_list_sheets_rejected(multi_sheet_xlsx):
    with pytest.raises(SystemExit):
        parse_command_line(["--all-sheets", "--list-sheets", str(multi_sheet_xlsx)])


def test_all_sheets_combined_with_list_formats_rejected():
    with pytest.raises(SystemExit):
        parse_command_line(["--all-sheets", "--list-formats"])


def test_stdin_keeps_every_sheet(multi_sheet_xlsx, capsys):
    rc = cli(
        ["--all-sheets", "-t", "json", "-", "-f", "xlsx"],
        stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()),
    )
    assert rc == 0
    book = json.loads(capsys.readouterr().out)
    assert [sheet["title"] for sheet in book] == ["people", "cities"]


def test_all_sheets_multiple_inputs_rejected(sample_csv, sample_json, tmp_path):
    out = tmp_path / "out.xlsx"
    with pytest.raises(SystemExit):
        parse_command_line(
            ["--all-sheets", "-o", str(out), str(sample_csv), str(sample_json)]
        )


# --- default mode on a multi-sheet input ---


# Default mode: whole-book conversion, first-sheet print, no silent loss.

# terminal print + advice


def test_print_shows_first_sheet_only(multi_sheet_xlsx, capsys):
    rc = cli([str(multi_sheet_xlsx)], stderr_isatty=False)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Alice" in out
    assert "Stockholm" not in out
    assert "===" not in out


def test_advice_on_tty(multi_sheet_xlsx, capsys):
    cli([str(multi_sheet_xlsx)], stderr_isatty=True)
    err = capsys.readouterr().err
    assert f"{multi_sheet_xlsx}: 1 more sheet(s)" in err
    assert "-l to list" in err
    assert "-s to pick" in err
    assert "--all-sheets for all" in err


def test_no_advice_when_piped(multi_sheet_xlsx, capsys):
    """Advice is for a watching human; in a pipe it is only noise."""
    cli([str(multi_sheet_xlsx)], stderr_isatty=False)
    assert capsys.readouterr().err == ""


def test_advice_counts_remaining_sheets(multi_sheet_json, capsys):
    cli([str(multi_sheet_json)], stderr_isatty=True)
    assert "2 more sheet(s)" in capsys.readouterr().err


def test_stdout_identical_regardless_of_tty(multi_sheet_xlsx, capsys):
    """The gate must affect stderr only."""
    cli([str(multi_sheet_xlsx)], stderr_isatty=True)
    on_tty = capsys.readouterr().out
    cli([str(multi_sheet_xlsx)], stderr_isatty=False)
    assert capsys.readouterr().out == on_tty


def test_no_advice_for_one_sheet_workbook(one_sheet_xlsx, capsys):
    rc = cli([str(one_sheet_xlsx)], stderr_isatty=True)
    captured = capsys.readouterr()
    assert rc == 0
    assert "Alice" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("fixture", ["sample_csv", "sample_json"])
def test_no_advice_for_structureless_input(fixture, request, capsys):
    path = request.getfixturevalue(fixture)
    rc = cli([str(path)], stderr_isatty=True)
    captured = capsys.readouterr()
    assert rc == 0
    assert "Alice" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("flags", [["-s", "0"], ["--all-sheets"]])
def test_no_advice_with_selection_flags(flags, multi_sheet_xlsx, capsys):
    """Selection takes another dispatch path, so the advice is suppressed."""
    rc = cli([*flags, str(multi_sheet_xlsx)], stderr_isatty=True)
    assert rc == 0
    assert capsys.readouterr().err == ""


def test_no_advice_with_list_sheets(multi_sheet_xlsx, capsys):
    rc = cli(["-l", str(multi_sheet_xlsx)], stderr_isatty=True)
    captured = capsys.readouterr()
    assert rc == 0
    assert "[0] people" in captured.out
    assert captured.err == ""


# whole-book conversion


def test_save_keeps_all_sheets(multi_sheet_json, tmp_path, capsys):
    out_file = tmp_path / "out.xlsx"
    rc = cli(["-o", str(out_file), str(multi_sheet_json)], stderr_isatty=True)
    captured = capsys.readouterr()
    assert rc == 0
    loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
    assert loaded.size == 3
    assert "3 sheets" in captured.out
    assert captured.err == ""


def test_export_keeps_all_sheets(multi_sheet_xlsx, capsys):
    rc = cli(["-t", "json", str(multi_sheet_xlsx)], stderr_isatty=False)
    captured = capsys.readouterr()
    assert rc == 0
    book = json.loads(captured.out)
    assert [sheet["title"] for sheet in book] == ["people", "cities"]
    assert captured.err == ""


def test_save_json_uses_book_shape(multi_sheet_xlsx, tmp_path):
    out_file = tmp_path / "out.json"
    cli(["-o", str(out_file), str(multi_sheet_xlsx)], stderr_isatty=False)
    book = json.loads(out_file.read_text())
    assert [sheet["title"] for sheet in book] == ["people", "cities"]


def test_positional_outfile_keeps_all_sheets(multi_sheet_xlsx, tmp_path):
    """The two-positional style is the same conversion path as -o."""
    out_file = tmp_path / "out.xlsx"
    rc = cli([str(multi_sheet_xlsx), str(out_file)], stderr_isatty=False)
    assert rc == 0
    loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
    assert loaded.size == 2


# fallback + unconditional data-loss warning


@pytest.mark.parametrize("isatty", [True, False])
def test_export_csv_falls_back_with_warning(isatty, multi_sheet_xlsx, capsys):
    """Dropping sheets is a correctness issue, so the warning is ungated."""
    rc = cli(["-t", "csv", str(multi_sheet_xlsx)], stderr_isatty=isatty)
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.startswith("name,age")
    assert "Stockholm" not in captured.out
    assert f"{multi_sheet_xlsx}: format 'csv' cannot hold all 2 sheets" in (
        captured.err
    )
    assert "converting only the first" in captured.err
    assert "use -s to choose" in captured.err


def test_fallback_never_suggests_all_sheets(multi_sheet_xlsx, capsys):
    """--all-sheets errors in this same situation, so it must not be advised."""
    cli(["-t", "csv", str(multi_sheet_xlsx)], stderr_isatty=True)
    assert "--all-sheets" not in capsys.readouterr().err


def test_save_csv_falls_back_cleanly(multi_sheet_xlsx, tmp_path, capsys):
    """The whole-book attempt truncates the target; the fallback rewrites it."""
    out_file = tmp_path / "out.csv"
    rc = cli(["-o", str(out_file), str(multi_sheet_xlsx)], stderr_isatty=False)
    captured = capsys.readouterr()
    assert rc == 0
    assert "cannot hold all 2 sheets" in captured.err
    assert "2 records" in captured.out
    text = out_file.read_text()
    assert text.startswith("name,age")
    assert "Stockholm" not in text
    assert len(text.strip().splitlines()) == 3


def test_fallback_names_the_attempted_format(multi_sheet_xlsx, tmp_path, capsys):
    """-t wins over the extension, so the warning must name -t's format."""
    out_file = tmp_path / "out.dat"
    rc = cli(
        ["-o", str(out_file), "-t", "csv", str(multi_sheet_xlsx)],
        stderr_isatty=False,
    )
    err = capsys.readouterr().err
    assert rc == 0
    assert "format 'csv'" in err
    assert "'dat'" not in err


def test_fallback_to_cli_matches_bare_print(multi_sheet_xlsx, capsys):
    """Stdout stays identical; only stderr distinguishes view from conversion."""
    cli([str(multi_sheet_xlsx)], stderr_isatty=True)
    printed = capsys.readouterr()
    cli(["-t", "cli", str(multi_sheet_xlsx)], stderr_isatty=True)
    exported = capsys.readouterr()
    assert exported.out == printed.out
    assert "more sheet(s)" in printed.err
    assert "cannot hold all" in exported.err


# unrelated errors are not swallowed


def test_undetectable_target_format_not_swallowed(multi_sheet_xlsx, tmp_path, capsys):
    out_file = tmp_path / "out.zzz"
    with pytest.raises(SystemExit) as excinfo:
        cli(["-o", str(out_file), str(multi_sheet_xlsx)], stderr_isatty=False)
    msg = str(excinfo.value)
    assert "Unable to detect target file format" in msg
    assert "cannot hold" not in msg
    assert "cannot hold" not in capsys.readouterr().err
    assert not out_file.exists()


def test_all_sheets_still_errors_where_default_falls_back(multi_sheet_xlsx, tmp_path):
    """Explicit flags stay strict; only the default is best-effort."""
    out_file = tmp_path / "out.csv"
    with pytest.raises(SystemExit) as excinfo:
        cli(["--all-sheets", "-o", str(out_file), str(multi_sheet_xlsx)])
    assert "pick one sheet with --sheet" in str(excinfo.value)


def test_failed_all_sheets_save_leaves_outfile_untouched(multi_sheet_xlsx, tmp_path):
    """A save the target format refuses must not destroy the existing file."""
    out_file = tmp_path / "out.csv"
    out_file.write_text("sentinel")
    with pytest.raises(SystemExit):
        cli(["-y", "--all-sheets", "-o", str(out_file), str(multi_sheet_xlsx)])
    assert out_file.read_text() == "sentinel"


# degenerate inputs


def test_empty_workbook_names_the_source(empty_workbook):
    """The default path names the file it read; selection reports structure."""
    with pytest.raises(SystemExit) as excinfo:
        cli([str(empty_workbook)], stderr_isatty=False)
    assert f"No data was loaded from {empty_workbook}" in str(excinfo.value)


def test_one_sheet_json_book_renders_its_sheet(year_title_json, capsys):
    """Previously this printed a bogus two-column title/data table."""
    rc = cli([str(year_title_json)], stderr_isatty=True)
    captured = capsys.readouterr()
    assert rc == 0
    assert "month" in captured.out
    assert "Jan" in captured.out
    assert "data" not in captured.out
    assert captured.err == ""


def test_headers_only_csv_still_reports_no_data(tmp_path):
    p = tmp_path / "hdr.csv"
    p.write_text("a,b\n")
    with pytest.raises(SystemExit) as excinfo:
        cli([str(p)], stderr_isatty=False)
    assert f"No data was loaded from {p}" in str(excinfo.value)


def test_empty_first_sheet_advises_without_error(tmp_path, capsys):
    """The book has data even when its first sheet does not."""
    p = tmp_path / "sparse.json"
    p.write_text(
        json.dumps(
            [
                {"title": "blank", "data": []},
                {"title": "full", "data": [{"name": "Alice"}]},
            ]
        )
    )
    rc = cli([str(p)], stderr_isatty=True)
    assert rc == 0
    assert "1 more sheet(s)" in capsys.readouterr().err


# stdin reads exactly like a file argument


def test_stdin_multi_sheet_keeps_all_sheets(multi_sheet_xlsx, capsys):
    rc = cli(
        ["-", "-f", "xlsx", "-t", "json"],
        stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()),
        stderr_isatty=False,
    )
    captured = capsys.readouterr()
    assert rc == 0
    book = json.loads(captured.out)
    assert [sheet["title"] for sheet in book] == ["people", "cities"]
    assert captured.err == ""


def test_stdin_multi_sheet_fallback_warns(multi_sheet_xlsx, capsys):
    rc = cli(
        ["-", "-f", "xlsx", "-t", "csv"],
        stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()),
        stderr_isatty=False,
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "stdin: format 'csv' cannot hold all 2 sheets" in captured.err
    assert captured.out.startswith("name,age")


def test_stdin_csv_unchanged(capsys):
    rc = cli(
        ["-", "-t", "json"],
        stdin=io.BytesIO(b"name,age\nAlice,30\n"),
        stderr_isatty=True,
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == [{"name": "Alice", "age": "30"}]
    assert captured.err == ""


# --- terminal print rendering ---


def _without_cli_format(monkeypatch):
    """Simulate an install where tablib has no "cli" format registered."""
    formats = tuple(f for f in get_formats() if f != "cli")
    monkeypatch.setattr("tublub.main.get_formats", lambda: formats)


def test_default_print_matches_t_cli(sample_csv, capsys):
    cli([str(sample_csv)])
    printed = capsys.readouterr().out
    cli(["-t", "cli", str(sample_csv)])
    exported = capsys.readouterr().out
    assert printed == exported


def test_default_print_matches_t_cli_with_tablefmt(sample_csv, capsys):
    cli(["--tablefmt", "grid", str(sample_csv)])
    printed = capsys.readouterr().out
    cli(["--tablefmt", "grid", "-t", "cli", str(sample_csv)])
    exported = capsys.readouterr().out
    assert printed == exported
    assert "+---" in printed


def test_default_style_is_tabulate_plain(sample_csv, capsys):
    """Not tablib's __str__ table: no pipe separators, no dashed rule."""
    cli([str(sample_csv)])
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "|" not in out
    assert "---" not in out


@pytest.mark.parametrize("fmt", ["cli", "json"])
def test_text_export_to_stdout_ends_with_one_newline(sample_csv, capsys, fmt):
    cli(["-t", fmt, str(sample_csv)])
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_saved_file_has_no_added_newline(sample_csv, tmp_path):
    """The newline is a stdout courtesy; -o writes the payload verbatim."""
    out_file = tmp_path / "out.json"
    cli(["-o", str(out_file), str(sample_csv)])
    assert not out_file.read_text().endswith("\n")


def test_falls_back_to_builtin_table_without_cli_format(
    sample_csv, capsys, monkeypatch
):
    _without_cli_format(monkeypatch)
    cli([str(sample_csv)])
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "|" in out  # tablib's own __str__ joins columns with pipes


def test_multi_sheet_print_falls_back_too(multi_sheet_xlsx, capsys, monkeypatch):
    _without_cli_format(monkeypatch)
    cli(["--all-sheets", str(multi_sheet_xlsx)])
    out = capsys.readouterr().out
    assert "=== people (2 rows) ===" in out
    assert "|" in out


# --- output clobber guard ---


def test_clobber_flags_default_off(sample_csv):
    args, _ = parse_command_line([str(sample_csv)])
    assert args.yes is False
    assert args.no_clobber is False


@pytest.mark.parametrize(
    ("flag", "dest"),
    [
        ("-y", "yes"),
        ("--yes", "yes"),
        ("-n", "no_clobber"),
        ("--no-clobber", "no_clobber"),
    ],
)
def test_clobber_flag_spellings(sample_csv, flag, dest):
    args, _ = parse_command_line([flag, str(sample_csv)])
    assert getattr(args, dest) is True


def test_no_clobber_with_yes_rejected(sample_csv, capsys):
    with pytest.raises(SystemExit):
        parse_command_line(["-n", "-y", str(sample_csv)])
    assert "Can not combine" in capsys.readouterr().err


# refusing to overwrite


def test_no_clobber_refuses_existing(existing_out, sample_csv):
    with pytest.raises(SystemExit) as excinfo:
        cli(["-n", "-o", str(existing_out), str(sample_csv)])
    message = str(excinfo.value)
    assert "already exists" in message
    assert "-y" in message
    assert existing_out.read_text() == "sentinel"


def test_default_refuses_when_not_tty(existing_out, sample_csv, capsys):
    """A script cannot answer a question, so it must opt in with -y."""
    with pytest.raises(SystemExit) as excinfo:
        cli(["-o", str(existing_out), str(sample_csv)], stdin_isatty=False)
    assert "-y" in str(excinfo.value)
    assert existing_out.read_text() == "sentinel"
    assert "Overwrite?" not in capsys.readouterr().err


def test_positional_outfile_guarded(existing_out, sample_csv):
    """The two-positional form is the easiest way to clobber by accident."""
    with pytest.raises(SystemExit):
        cli([str(sample_csv), str(existing_out)], stdin_isatty=False)
    assert existing_out.read_text() == "sentinel"


def test_multi_input_output_guarded(existing_out, sample_csv, sample_json):
    with pytest.raises(SystemExit):
        cli(
            ["-o", str(existing_out), str(sample_csv), str(sample_json)],
            stdin_isatty=False,
        )
    assert existing_out.read_text() == "sentinel"


# overwriting on purpose


def test_yes_overwrites_existing(existing_out, sample_csv, capsys):
    rc = cli(["-y", "-o", str(existing_out), str(sample_csv)], stdin_isatty=False)
    assert rc == 0
    assert "Alice" in existing_out.read_text()
    assert "Overwrite?" not in capsys.readouterr().err


@pytest.mark.parametrize("answer", ["y\n", "Y\n", "yes\n", " y \n"])
def test_prompt_yes_overwrites(existing_out, sample_csv, capsys, answer):
    rc = cli(
        ["-o", str(existing_out), str(sample_csv)],
        stdin_isatty=True,
        prompt_input=io.StringIO(answer),
    )
    assert rc == 0
    assert "Alice" in existing_out.read_text()
    captured = capsys.readouterr()
    assert "Overwrite? [y/N]" in captured.err
    assert "Overwrite?" not in captured.out


@pytest.mark.parametrize("answer", ["n\n", "no\n", "\n", ""])
def test_prompt_declined_refuses(existing_out, sample_csv, answer):
    """Anything but yes keeps the file, including a bare newline and EOF."""
    with pytest.raises(SystemExit):
        cli(
            ["-o", str(existing_out), str(sample_csv)],
            stdin_isatty=True,
            prompt_input=io.StringIO(answer),
        )
    assert existing_out.read_text() == "sentinel"


# nothing to clobber


@pytest.mark.parametrize("flags", [[], ["-y"], ["-n"]])
def test_fresh_outfile_skips_check(sample_csv, tmp_path, flags):
    out_file = tmp_path / "fresh.json"
    rc = cli([*flags, "-o", str(out_file), str(sample_csv)], stdin_isatty=False)
    assert rc == 0
    assert "Alice" in out_file.read_text()


@pytest.mark.parametrize("flags", [[], ["-y"], ["-n"]])
def test_stdout_output_unaffected(sample_csv, capsys, flags):
    rc = cli([*flags, "-t", "json", str(sample_csv)], stdin_isatty=False)
    assert rc == 0
    assert "Alice" in capsys.readouterr().out


# --- single-input sheet titling ---


def _saved_titles(out_file):
    """Reload a saved XLSX workbook and return its sheet titles."""
    book = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
    return [sheet.title for sheet in book.sheets()]


def test_single_file_sheet_named_after_stem(sample_csv, tmp_path):
    out_file = tmp_path / "out.xlsx"
    rc = cli([str(sample_csv), str(out_file)])
    assert rc == 0
    assert _saved_titles(out_file) == ["data"]


def test_stdin_sheet_named_stdin(tmp_path):
    out_file = tmp_path / "out.xlsx"
    rc = cli(["-", str(out_file)], stdin=io.BytesIO(b"name,age\nAlice,30\n"))
    assert rc == 0
    assert _saved_titles(out_file) == ["stdin"]


def test_long_stem_clamped_to_limit(tmp_path):
    long_input = tmp_path / f"{'x' * 40}.csv"
    long_input.write_text("name,age\nAlice,30\n")
    out_file = tmp_path / "out.xlsx"
    rc = cli([str(long_input), str(out_file)])
    assert rc == 0
    assert _saved_titles(out_file) == ["x" * XLSX_TITLE_LIMIT]


def test_observed_sheet_title_survives(one_sheet_xlsx, tmp_path):
    """A one-sheet workbook keeps its own title; only structureless input is named."""
    out_file = tmp_path / "out.xlsx"
    rc = cli([str(one_sheet_xlsx), str(out_file)])
    assert rc == 0
    assert _saved_titles(out_file) == ["people"]


def test_all_sheets_titles_structureless_input_too(sample_csv, tmp_path):
    """--all-sheets is the identity modifier here, so the naming must match."""
    out_file = tmp_path / "out.xlsx"
    rc = cli(["--all-sheets", "-o", str(out_file), str(sample_csv)])
    assert rc == 0
    assert _saved_titles(out_file) == ["data"]


# --- man page ---


def test_man_page_documents_every_long_option():
    """The man page is the flag reference, so --help must not outgrow it."""
    man_page = Path(__file__).parent.parent / "docs" / "tublub.1.md"
    source = man_page.read_text(encoding="utf-8")
    flags = set(re.findall(r"--[a-z][a-z-]+", build_argument_parser().format_help()))
    assert flags, "no long options found in --help; the regex is wrong"
    missing = sorted(flag for flag in flags if flag not in source)
    assert not missing, f"undocumented in {man_page.name}: {', '.join(missing)}"
