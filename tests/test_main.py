"""Tests for tublub.main."""

import io
import json
from pathlib import Path

import pytest
import tablib

from tublub.main import (
    FORMATS,
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


class TestGuessFileFormat:
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
    def test_known_extensions(self, filename, expected):
        assert guess_file_format(Path(filename)) == expected

    @pytest.mark.parametrize("filename", ["data.xyz", "datafile"])
    def test_unknown_or_missing_extension(self, filename):
        assert guess_file_format(Path(filename)) is None

    def test_none_input(self):
        assert guess_file_format(None) is None


# --- is_bin ---


class TestIsBin:
    @pytest.mark.parametrize("fmt", sorted(k for k, v in FORMATS.items() if v.binary))
    def test_binary_formats(self, fmt):
        assert is_bin(fmt) is True

    @pytest.mark.parametrize("fmt", ["csv", "tsv", "json", "yaml", "html"])
    def test_text_formats(self, fmt):
        assert is_bin(fmt) is False

    def test_none(self):
        assert is_bin(None) is False

    def test_empty(self):
        assert is_bin("") is False


# --- filter_args ---


class TestFilterArgs:
    def test_filters_to_matching_format(self):
        user_args = {"skip_lines": 2, "delimiter": ","}
        result = filter_args("load", user_args, "csv")
        assert result == {"skip_lines": 2, "delimiter": ","}

    def test_excludes_irrelevant_args(self):
        user_args = {"skip_lines": 2, "delimiter": ","}
        result = filter_args("load", user_args, "xlsx")
        assert result == {"skip_lines": 2}
        assert "delimiter" not in result

    def test_unknown_format_returns_empty(self):
        user_args = {"skip_lines": 2}
        result = filter_args("load", user_args, "json")
        assert result == {}

    def test_none_values_excluded(self):
        user_args = {"skip_lines": None, "delimiter": ","}
        result = filter_args("load", user_args, "csv")
        assert result == {"delimiter": ","}

    def test_empty_user_args(self):
        result = filter_args("load", {}, "csv")
        assert result == {}

    def test_save_extra_args(self):
        user_args = {"tablefmt": "fancy_grid"}
        result = filter_args("save", user_args, "cli")
        assert result == {"tablefmt": "fancy_grid"}


# --- get_formats ---


class TestGetFormats:
    def test_returns_tuple(self):
        assert isinstance(get_formats(), tuple)

    def test_includes_common_formats(self):
        formats = get_formats()
        for fmt in ("csv", "json", "xlsx", "yaml", "tsv"):
            assert fmt in formats

    def test_cached(self):
        assert get_formats() is get_formats()


# --- _looks_like_text_lines ---


class TestLooksLikeTextLines:
    """Unit tests for the single-column text heuristic."""

    def test_single_column_data(self):
        assert _looks_like_text_lines("name\nAlice\nBob\n") is True

    def test_single_line_rejected(self):
        assert _looks_like_text_lines("hello") is False

    def test_empty_string_rejected(self):
        assert _looks_like_text_lines("") is False

    def test_whitespace_only_rejected(self):
        assert _looks_like_text_lines("  \n  \n") is False

    @pytest.mark.parametrize("delimiter", [",", "\t", ";", "|"])
    def test_delimited_data_rejected(self, delimiter):
        text = f"a{delimiter}b\n1{delimiter}2\n"
        assert _looks_like_text_lines(text) is False

    def test_prose_with_commas_rejected(self):
        assert _looks_like_text_lines("Hello, world.\nDear sir, ...\n") is False


# --- load_dataset_file ---


class TestLoadDatasetFile:
    @pytest.mark.parametrize(
        "fixture",
        ["sample_csv", "sample_json", "sample_tsv", "sample_yaml"],
    )
    def test_load_formats(self, fixture, request):
        path = request.getfixturevalue(fixture)
        ds = load_dataset_file(path, extra_args={})
        assert len(ds) == 2
        assert ds.headers is not None
        assert "name" in ds.headers

    def test_load_csv_with_skip_lines(self, tmp_path):
        p = tmp_path / "skip.csv"
        p.write_text("# comment\nname,age\nAlice,30\n")
        ds = load_dataset_file(p, extra_args={"skip_lines": 1})
        assert len(ds) == 1
        assert ds.headers == ["name", "age"]

    def test_load_csv_with_delimiter(self, tmp_path):
        p = tmp_path / "semi.csv"
        p.write_text("name;age\nAlice;30\n")
        ds = load_dataset_file(p, extra_args={"delimiter": ";"})
        assert len(ds) == 1
        assert ds.headers == ["name", "age"]

    def test_load_csv_no_extension(self, tmp_path):
        """CSV file without extension should be detected via text-mode fallback."""
        p = tmp_path / "data"
        p.write_text("name,age,city\nAlice,30,Stockholm\nBob,25,Gothenburg\n")
        ds = load_dataset_file(p, extra_args={})
        assert len(ds) == 2
        assert ds.headers == ["name", "age", "city"]

    def test_load_xlsx_no_extension(self, tmp_path, sample_data):
        """XLSX file without extension should be detected via binary-mode pass."""
        p = tmp_path / "data"
        p.write_bytes(sample_data.export("xlsx"))
        ds = load_dataset_file(p, extra_args={})
        assert len(ds) == 2

    def test_load_single_column_txt(self, tmp_path):
        """Single-column data in a .txt file should be detected via heuristic."""
        p = tmp_path / "names.txt"
        p.write_text("name\nAlice\nBob\n")
        ds = load_dataset_file(p, extra_args={})
        assert len(ds) == 2
        assert ds.headers == ["name"]

    def test_load_single_column_no_extension(self, tmp_path):
        """Single-column data without extension should be detected via heuristic."""
        p = tmp_path / "data"
        p.write_text("name\nAlice\nBob\n")
        ds = load_dataset_file(p, extra_args={})
        assert len(ds) == 2
        assert ds.headers == ["name"]

    def test_load_in_format_overrides_detection(self, tmp_path):
        """-f flag should override both detection and extension."""
        p = tmp_path / "data.txt"
        p.write_text("name,age\nAlice,30\n")
        ds = load_dataset_file(p, extra_args={}, in_format="csv")
        assert ds.headers == ["name", "age"]

    def test_load_unknown_format_raises(self, tmp_path):
        p = tmp_path / "data.xyz"
        p.write_text("not a known format")
        with pytest.raises(TublubError, match="Unable to detect"):
            load_dataset_file(p, extra_args={})


# --- save_dataset_file ---


class TestSaveDatasetFile:
    @pytest.mark.parametrize("fmt", ["csv", "json", "yaml"])
    def test_save_formats(self, sample_data, tmp_path, fmt):
        out = tmp_path / f"out.{fmt}"
        save_dataset_file(sample_data, out, extra_args={})
        assert "Alice" in out.read_text()

    def test_save_unknown_format_raises(self, sample_data, tmp_path):
        out = tmp_path / "out.xyz"
        with pytest.raises(TublubError, match="Unable to detect"):
            save_dataset_file(sample_data, out, extra_args={})

    def test_roundtrip_csv(self, sample_data, tmp_path):
        out = tmp_path / "roundtrip.csv"
        save_dataset_file(sample_data, out, extra_args={})
        loaded = load_dataset_file(out, extra_args={})
        assert loaded.headers == sample_data.headers
        assert len(loaded) == len(sample_data)


# --- export_dataset ---


class TestExportDataset:
    def test_export_to_file_handle(self, sample_data, tmp_path):
        out = tmp_path / "export.csv"
        with out.open("w", newline="") as fh:
            export_dataset(sample_data, "csv", extra_args={}, file_handle=fh)
        content = out.read_text()
        assert "Alice" in content

    def test_default_handle_binary_to_tty_raises(self):
        class TTYStdout(io.TextIOWrapper):
            def isatty(self):
                return True

        with pytest.raises(TublubError, match="binary"):
            _default_export_handle("xlsx", stdout=TTYStdout(io.BytesIO()))

    def test_default_handle_binary_to_piped_stdout(self, sample_data):
        """Binary export to non-TTY stdout should use stdout.buffer."""
        raw = io.BytesIO()
        stdout = io.TextIOWrapper(raw)  # kept alive: GC would close raw
        handle = _default_export_handle("xlsx", stdout=stdout)
        export_dataset(sample_data, "xlsx", extra_args={}, file_handle=handle)
        assert raw.getvalue().startswith(b"PK")  # XLSX is a zip container

    def test_default_handle_text_returns_stream(self):
        stream = io.StringIO()
        assert _default_export_handle("json", stdout=stream) is stream

    def test_export_text_to_non_tty(self, sample_data, tmp_path):
        out = tmp_path / "piped.json"
        with out.open("w") as fh:
            export_dataset(sample_data, "json", extra_args={}, file_handle=fh)
        assert "Alice" in out.read_text()


# --- parse_command_line ---


class TestParseCommandLine:
    def test_list_formats_flag(self):
        args, extra = parse_command_line(["--list-formats"])
        assert args.list_formats is True

    def test_infile_only(self, sample_csv):
        args, extra = parse_command_line([str(sample_csv)])
        assert args.infiles == [sample_csv]
        assert args.outfile is None

    def test_infile_and_outfile(self, sample_csv, tmp_path):
        out = tmp_path / "out.json"
        args, extra = parse_command_line([str(sample_csv), str(out)])
        assert args.infiles == [sample_csv]
        assert args.outfile == out

    def test_format_flag(self, sample_csv):
        args, extra = parse_command_line(["-t", "json", str(sample_csv)])
        assert args.out_format == "json"

    def test_extra_args_collected(self, sample_csv):
        args, extra = parse_command_line(["--skip-lines", "2", str(sample_csv)])
        assert extra["skip_lines"] == 2

    def test_no_input_exits(self):
        with pytest.raises(SystemExit):
            parse_command_line([], stdin_isatty=True)

    def test_nonexistent_file_exits(self):
        with pytest.raises(SystemExit):
            parse_command_line(["/no/such/file.csv"])

    def test_invalid_format_exits(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["-t", "bogus", str(sample_csv)])

    def test_list_formats_with_file_exits(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-formats", str(sample_csv)])

    def test_from_flag_sets_in_format(self, sample_csv):
        args, _ = parse_command_line(["--from", "csv", str(sample_csv)])
        assert args.in_format == "csv"

    def test_to_flag_sets_out_format(self, sample_csv):
        args, _ = parse_command_line(["--to", "json", str(sample_csv)])
        assert args.out_format == "json"

    @pytest.mark.parametrize("flag", ["--list", "--in-format", "--format"])
    def test_dropped_spellings_rejected(self, sample_csv, flag):
        """The old long forms fail loud, never silently change meaning."""
        with pytest.raises(SystemExit):
            parse_command_line([flag, "csv", str(sample_csv)])

    def test_bare_l_requires_input_file(self):
        """-l is now --list-sheets, so it needs an input file."""
        with pytest.raises(SystemExit):
            parse_command_line(["-l"], stdin_isatty=True)

    def test_delimiter_extra_arg(self, sample_csv):
        args, extra = parse_command_line(["-d", ";", str(sample_csv)])
        assert extra["delimiter"] == ";"

    @pytest.mark.parametrize(
        ("flag", "key"),
        [("-H", "headers"), ("--no-xlsx-optimize", "read_only")],
    )
    def test_store_const_flags(self, sample_csv, flag, key):
        """store_const flags should be absent by default, False when set."""
        _, extra_default = parse_command_line([str(sample_csv)])
        assert key not in extra_default
        _, extra_set = parse_command_line([flag, str(sample_csv)])
        assert extra_set[key] is False


# --- build_argument_parser ---


class TestBuildArgumentParser:
    def test_returns_parser(self):
        parser = build_argument_parser()
        assert isinstance(parser, type(build_argument_parser()))

    def test_version_flag(self, capsys):
        parser = build_argument_parser()
        with pytest.raises(SystemExit, match="0"):
            parser.parse_args(["--version"])


# --- load_dataset_stdin ---


class TestLoadDatasetStdin:
    @pytest.mark.parametrize("fmt", ["csv", "json", "xlsx"])
    def test_auto_detect(self, sample_data, fmt):
        raw = sample_data.export(fmt)
        if isinstance(raw, str):
            raw = raw.encode()
        ds = load_dataset_stdin(stdin=io.BytesIO(raw))
        assert len(ds) == 2
        assert ds.headers is not None
        assert "name" in ds.headers

    def test_explicit_format(self):
        csv_bytes = b"name,age\nAlice,30\n"
        ds = load_dataset_stdin(in_format="csv", stdin=io.BytesIO(csv_bytes))
        assert len(ds) == 1

    def test_extra_args_passed(self):
        csv_bytes = b"# comment\nname,age\nAlice,30\n"
        ds = load_dataset_stdin(
            in_format="csv",
            extra_args={"skip_lines": 1},
            stdin=io.BytesIO(csv_bytes),
        )
        assert len(ds) == 1
        assert ds.headers == ["name", "age"]

    def test_empty_stdin_raises(self):
        with pytest.raises(TublubError, match="No data received"):
            load_dataset_stdin(stdin=io.BytesIO(b""))

    def test_single_column_heuristic(self):
        """Single-column data on stdin should be detected as TSV via heuristic."""
        ds = load_dataset_stdin(stdin=io.BytesIO(b"name\nAlice\nBob\n"))
        assert len(ds) == 2
        assert ds.headers == ["name"]

    def test_undetectable_format_raises(self):
        with pytest.raises(TublubError, match=r"Unable to detect.*-f"):
            load_dataset_stdin(stdin=io.BytesIO(b"???"))


# --- parse_command_line stdin ---


class TestParseCommandLineStdin:
    def test_dash_sets_stdin_flag(self):
        args, _ = parse_command_line(["-", "-t", "json"], stdin_isatty=True)
        assert args.stdin is True
        assert args.infiles == []

    def test_implicit_stdin_when_piped(self):
        args, _ = parse_command_line(["-t", "json"], stdin_isatty=False)
        assert args.stdin is True

    def test_no_implicit_stdin_on_tty(self):
        """An interactive TTY with no input is a usage error, not stdin."""
        with pytest.raises(SystemExit):
            parse_command_line(["-t", "json"], stdin_isatty=True)

    def test_in_format_flag(self):
        args, _ = parse_command_line(["-f", "csv", "-t", "json"], stdin_isatty=False)
        assert args.in_format == "csv"

    def test_invalid_in_format_exits(self):
        with pytest.raises(SystemExit):
            parse_command_line(["-f", "bogus", "-t", "json"], stdin_isatty=False)

    def test_in_format_with_file(self, sample_csv):
        args, _ = parse_command_line(["-f", "csv", str(sample_csv)])
        assert args.in_format == "csv"
        assert args.stdin is False


# --- _unique_titles ---


class TestUniqueTitles:
    def test_distinct_titles(self):
        entries = [("a", "d_a"), ("b", "d_b"), ("c", "d_c")]
        assert _unique_titles(entries) == ["a", "b", "c"]

    def test_collision_uses_qualified(self, capsys):
        entries = [("sales", "d1_sales"), ("sales", "d2_sales")]
        assert _unique_titles(entries) == ["d1_sales", "d2_sales"]
        assert "disambiguated" in capsys.readouterr().err

    def test_triple_collision_uses_qualified(self):
        entries = [("x", "a_x"), ("x", "b_x"), ("x", "c_x")]
        assert _unique_titles(entries) == ["a_x", "b_x", "c_x"]

    def test_mixed_collisions(self):
        # Clashes are counted per preferred title: "users" keeps its own name
        # even though the other three entries fall back to qualified forms.
        entries = [
            ("sales", "a_sales"),
            ("users", "d_users"),
            ("sales", "b_sales"),
            ("sales", "c_sales"),
        ]
        assert _unique_titles(entries) == ["a_sales", "users", "b_sales", "c_sales"]

    def test_qualified_collision_falls_back_to_numeric_suffix(self):
        # Both entries qualify to the same name (same parent dir name, or
        # two same-titled sheets in one workbook) → the _2 suffix kicks in.
        entries = [("x", "data_x"), ("x", "data_x")]
        assert _unique_titles(entries) == ["data_x", "data_x_2"]

    def test_unqualifiable_entry_falls_back_to_numeric_suffix(self, capsys):
        # A path with no parent name qualifies to its own stem.
        entries = [("Sales", "Sales"), ("Sales", "dir_Sales")]
        assert _unique_titles(entries) == ["Sales", "dir_Sales"]
        assert "disambiguated" in capsys.readouterr().err

    def test_no_collision_no_note(self, capsys):
        _unique_titles([("a", "d_a"), ("b", "d_b")])
        assert capsys.readouterr().err == ""

    def test_empty(self):
        assert _unique_titles([]) == []

    def test_long_title_truncated_to_limit(self, capsys):
        long = "a" * 40
        titles = _unique_titles([(long, long)])
        assert titles == ["a" * 31]
        assert "disambiguated" in capsys.readouterr().err

    def test_long_shared_prefix_stays_unique(self):
        # Two distinct titles sharing a >31-char prefix clamp to the same 31
        # chars, so the _2 suffix kicks in with the base trimmed to fit.
        prefix = "x" * 40
        entries = [(f"{prefix}A", f"{prefix}A"), (f"{prefix}B", f"{prefix}B")]
        titles = _unique_titles(entries)
        assert all(len(t) <= 31 for t in titles)
        assert titles == ["x" * 31, "x" * 29 + "_2"]


# --- build_databook ---


class TestBuildDatabook:
    def test_two_inputs(self, sample_csv, sample_json):
        book = build_databook([sample_csv, sample_json], extra_args={})
        assert book.size == 2
        titles = [s.title for s in book.sheets()]
        # Both fixtures share stem "data" and parent dir, so disambiguation
        # falls back to a numeric suffix on the parent-qualified base.
        assert len(set(titles)) == 2
        assert all("data" in t for t in titles)

    def test_sheet_data_preserved(self, sample_csv, sample_json):
        book = build_databook([sample_csv, sample_json], extra_args={})
        sheets = book.sheets()
        assert sheets[0].headers == ["name", "age", "city"]
        assert len(sheets[0]) == 2
        assert len(sheets[1]) == 2

    def test_distinct_stems(self, tmp_path):
        a = tmp_path / "sales.csv"
        a.write_text("name,age\nAlice,30\n")
        b = tmp_path / "users.csv"
        b.write_text("name,age\nBob,25\n")
        book = build_databook([a, b], extra_args={})
        assert [s.title for s in book.sheets()] == ["sales", "users"]


# --- save_databook_file ---


class TestSaveDatabookFile:
    def test_save_xlsx(self, sample_csv, sample_json, tmp_path):
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

    def test_save_unsupported_format_raises(self, sample_csv, tmp_path):
        """CSV doesn't support Databook export — should raise TublubError."""
        out = tmp_path / "book.csv"
        book = build_databook([sample_csv, sample_csv], extra_args={})
        with pytest.raises(TublubError, match="multi-sheet"):
            save_databook_file(book, out, extra_args={})

    def test_save_unknown_format_raises(self, sample_csv, tmp_path):
        out = tmp_path / "book.xyz"
        book = build_databook([sample_csv, sample_csv], extra_args={})
        with pytest.raises(TublubError, match="Unable to detect"):
            save_databook_file(book, out, extra_args={})

    def test_force_format_overrides_extension(self, sample_csv, tmp_path):
        out = tmp_path / "book.bin"
        book = build_databook([sample_csv, sample_csv], extra_args={})
        save_databook_file(book, out, extra_args={}, force_format="xlsx")
        loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
        assert loaded.size == 2


# --- MultiSheetUnsupportedError ---


class TestMultiSheetUnsupportedError:
    def test_export_raises_subclass_carrying_the_format(self, sample_csv):
        """The default-mode fallback needs the format that was attempted."""
        book = build_databook([sample_csv, sample_csv], extra_args={})
        with pytest.raises(MultiSheetUnsupportedError) as excinfo:
            export_databook(book, "csv", {}, file_handle=io.StringIO())
        assert issubclass(MultiSheetUnsupportedError, TublubError)
        assert excinfo.value.target_format == "csv"
        assert "does not support multi-sheet output" in str(excinfo.value)

    def test_hint_still_appended(self, sample_csv):
        book = build_databook([sample_csv, sample_csv], extra_args={})
        with pytest.raises(MultiSheetUnsupportedError) as excinfo:
            export_databook(
                book, "csv", {}, file_handle=io.StringIO(), hint="pick one sheet"
            )
        assert str(excinfo.value).endswith("; pick one sheet")

    def test_binary_to_tty_is_not_the_fallback_signal(self):
        """Only the unsupported-format failure may trigger a fallback."""

        class TTYStdout(io.TextIOWrapper):
            def isatty(self):
                return True

        with pytest.raises(TublubError) as excinfo:
            _default_export_handle("xlsx", stdout=TTYStdout(io.BytesIO()))
        assert not isinstance(excinfo.value, MultiSheetUnsupportedError)


# --- load_databook_file ---


class TestLoadDatabookFile:
    def test_multi_sheet_xlsx_returns_book(self, multi_sheet_xlsx):
        book = load_databook_file(multi_sheet_xlsx, extra_args={})
        assert book is not None
        assert book.size == 2
        assert [s.title for s in book.sheets()] == ["people", "cities"]

    def test_csv_returns_none(self, sample_csv):
        assert load_databook_file(sample_csv, extra_args={}) is None

    def test_tsv_returns_none(self, sample_tsv):
        assert load_databook_file(sample_tsv, extra_args={}) is None

    def test_records_json_returns_none(self, sample_json):
        """JSON of records (single-Dataset shape) is not a Databook."""
        assert load_databook_file(sample_json, extra_args={}) is None

    def test_records_yaml_returns_none(self, sample_yaml):
        """YAML of records (single-Dataset shape) is not a Databook."""
        assert load_databook_file(sample_yaml, extra_args={}) is None

    def test_malformed_xlsx_propagates_error(self, tmp_path):
        """Real load errors must propagate, not be swallowed as None."""
        bad = tmp_path / "bad.xlsx"
        bad.write_bytes(b"not really an xlsx file")
        # Underlying error comes from openpyxl/zipfile; we don't pin the
        # exact type, only that it's not silently None and not TublubError.
        with pytest.raises(Exception, match=r".+") as exc_info:
            load_databook_file(bad, extra_args={})
        assert not isinstance(exc_info.value, TublubError)

    def test_in_format_override(self, multi_sheet_xlsx):
        book = load_databook_file(multi_sheet_xlsx, extra_args={}, in_format="xlsx")
        assert book is not None
        assert book.size == 2

    def test_unknown_format_raises(self, tmp_path):
        bad = tmp_path / "data.xyz"
        bad.write_text("nothing")
        with pytest.raises(TublubError, match="Unable to detect"):
            load_databook_file(bad, extra_args={})

    def test_broken_json_syntax_propagates(self, tmp_path):
        """The (UnsupportedFormat, KeyError, TypeError) catch must not swallow
        a JSONDecodeError from a syntactically broken JSON file."""
        bad = tmp_path / "broken.json"
        bad.write_bytes(b'{"foo":')
        with pytest.raises(Exception, match=r".+") as exc_info:
            try_load_file(bad, extra_args={})
        assert not isinstance(exc_info.value, TublubError)
        assert isinstance(exc_info.value, ValueError)  # JSONDecodeError

    def test_tablib_hostile_json_shape_propagates(self, tmp_path):
        """JSON valid as syntax but not a Dataset or Databook shape must
        surface as an error (UnsupportedFormat), not silently fall back."""
        bad = tmp_path / "weird.json"
        bad.write_bytes(b'{"random": "object"}')
        with pytest.raises(tablib.UnsupportedFormat):
            try_load_file(bad, extra_args={})


# --- load_databook_stdin ---


class TestLoadDatabookStdin:
    def test_multi_sheet_xlsx_from_stdin(self, multi_sheet_xlsx):
        book = load_databook_stdin(stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()))
        assert book is not None
        assert book.size == 2

    def test_csv_from_stdin_returns_none(self):
        stdin = io.BytesIO(b"name,age\nAlice,30\nBob,25\n")
        assert load_databook_stdin(stdin=stdin) is None

    def test_empty_stdin_raises(self):
        with pytest.raises(TublubError, match="No data"):
            load_databook_stdin(stdin=io.BytesIO(b""))


# --- try_load_stdin ---


class TestTryLoadStdin:
    def test_multi_sheet_xlsx_returns_book(self, multi_sheet_xlsx):
        loaded = try_load_stdin(stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()))
        assert isinstance(loaded, tablib.Databook)
        assert loaded.size == 2

    def test_csv_returns_dataset(self):
        loaded = try_load_stdin(stdin=io.BytesIO(b"name,age\nAlice,30\n"))
        assert isinstance(loaded, tablib.Dataset)
        assert "Alice" in str(loaded)

    def test_empty_stdin_raises(self):
        with pytest.raises(TublubError, match="No data received"):
            try_load_stdin(stdin=io.BytesIO(b""))


# --- parse_command_line: multi-input mode ---


class TestParseCommandLineMultiInput:
    def test_o_flag_with_two_inputs(self, sample_csv, sample_json, tmp_path):
        out = tmp_path / "book.xlsx"
        args, _ = parse_command_line(
            ["-o", str(out), str(sample_csv), str(sample_json)]
        )
        assert args.infiles == [sample_csv, sample_json]
        assert args.outfile == out

    def test_o_flag_with_single_input(self, sample_csv, tmp_path):
        """Single input under -o populates args.infiles (single-file path)."""
        out = tmp_path / "out.json"
        args, _ = parse_command_line(["-o", str(out), str(sample_csv)])
        assert args.infiles == [sample_csv]
        assert args.outfile == out

    def test_three_positionals_without_o_exits(self, sample_csv, tmp_path):
        out = tmp_path / "out.json"
        with pytest.raises(SystemExit):
            parse_command_line([str(sample_csv), str(sample_csv), str(out)])

    def test_stdin_rejected_in_multi_input(self, sample_csv, tmp_path):
        out = tmp_path / "book.xlsx"
        with pytest.raises(SystemExit):
            parse_command_line(["-o", str(out), "-", str(sample_csv)])

    def test_o_with_no_inputs_and_tty_exits(self, tmp_path):
        out = tmp_path / "out.json"
        with pytest.raises(SystemExit):
            parse_command_line(["-o", str(out)], stdin_isatty=True)

    def test_nonexistent_input_in_multi_exits(self, sample_csv, tmp_path):
        out = tmp_path / "book.xlsx"
        with pytest.raises(SystemExit):
            parse_command_line(["-o", str(out), str(sample_csv), "/no/such/file.csv"])


# --- cli() integration: multi-input → Databook ---


class TestCliDatabook:
    def test_multi_input_to_xlsx(self, sample_csv, sample_json, tmp_path):
        out = tmp_path / "book.xlsx"
        rc = cli(["-o", str(out), str(sample_csv), str(sample_json)])
        assert rc == 0
        loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
        assert loaded.size == 2

    def test_unsupported_output_exits(self, sample_csv, tmp_path):
        out = tmp_path / "book.csv"
        with pytest.raises(SystemExit):
            cli(["-o", str(out), str(sample_csv), str(sample_csv)])


# --- multi-input sheet expansion ---


def _titles(*paths):
    return [s.title for s in build_databook(list(paths), extra_args={}).sheets()]


class TestMultiInputExpansion:
    def test_book_sheets_expand_alongside_dataset(self, multi_sheet_xlsx, sample_csv):
        assert _titles(multi_sheet_xlsx, sample_csv) == ["people", "cities", "data"]

    def test_no_note_when_titles_survive(self, multi_sheet_xlsx, sample_csv, capsys):
        _titles(multi_sheet_xlsx, sample_csv)
        assert capsys.readouterr().err == ""

    def test_one_sheet_book_keeps_its_title(self, one_sheet_xlsx, sample_csv):
        assert _titles(one_sheet_xlsx, sample_csv) == ["people", "data"]

    def test_clash_across_inputs_qualifies_by_stem(self, multi_sheet_xlsx, capsys):
        assert _titles(multi_sheet_xlsx, multi_sheet_xlsx) == [
            "book__people",
            "book__cities",
            "book__people_2",
            "book__cities_2",
        ]
        assert "disambiguated" in capsys.readouterr().err

    def test_clash_within_one_input(self, dup_title_json):
        assert _titles(dup_title_json) == ["dup__Users", "Costs", "dup__Users_2"]

    def test_dataset_title_clashing_with_sheet_title(self, multi_sheet_xlsx, tmp_path):
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

    def test_long_clashing_titles_clamped(self, tmp_path):
        rows = [{"a": 1}]
        title = "T" * 25
        path = tmp_path / f"{'s' * 20}.json"
        path.write_text(
            json.dumps([{"title": title, "data": rows}, {"title": title, "data": rows}])
        )
        titles = _titles(path)
        assert all(len(t) <= 31 for t in titles)
        assert len(set(titles)) == 2

    def test_untitled_sheet_expands(self, empty_title_json):
        assert _titles(empty_title_json) == ["", "named"]

    def test_empty_workbook_contributes_nothing(self, empty_workbook, sample_csv):
        assert _titles(empty_workbook, sample_csv) == ["data"]

    def test_all_inputs_empty_exits(self, empty_workbook, tmp_path):
        second = tmp_path / "other.json"
        second.write_text("[]")
        out = tmp_path / "out.xlsx"
        with pytest.raises(SystemExit):
            cli(["-o", str(out), str(empty_workbook), str(second)])

    def test_cli_round_trip(self, multi_sheet_xlsx, sample_csv, tmp_path):
        out = tmp_path / "merged.xlsx"
        assert cli(["-o", str(out), str(multi_sheet_xlsx), str(sample_csv)]) == 0
        loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
        assert [s.title for s in loaded.sheets()] == ["people", "cities", "data"]

    def test_sheet_flag_rejected_with_two_inputs(self, multi_sheet_xlsx, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(
                ["-o", "out.xlsx", "-s", "0", str(multi_sheet_xlsx), str(sample_csv)]
            )

    def test_all_sheets_rejected_with_two_inputs(self, multi_sheet_xlsx, sample_csv):
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


class TestListSheets:
    def test_argparse_flag(self, sample_csv):
        args, _ = parse_command_line(["--list-sheets", str(sample_csv)])
        assert args.list_sheets is True

    def test_xlsx_lists_all_sheets(self, multi_sheet_xlsx, capsys):
        rc = cli(["--list-sheets", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        lines = out.strip().splitlines()
        assert len(lines) == 2
        assert lines[0] == "[0] people  2 rows x 2 cols"
        assert lines[1] == "[1] cities  2 rows x 2 cols"

    def test_one_sheet_xlsx_keeps_index(self, one_sheet_xlsx, capsys):
        """A one-sheet workbook still has sheet structure, so [0] is shown."""
        rc = cli(["--list-sheets", str(one_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        assert out == "[0] people  2 rows x 2 cols\n"

    def test_csv_falls_back_to_dataset(self, sample_csv, capsys):
        """No sheet structure: one bare line, no index or title."""
        rc = cli(["--list-sheets", str(sample_csv)])
        out = capsys.readouterr().out
        assert rc == 0
        assert out == "2 rows x 3 cols\n"

    def test_records_json_falls_back_to_dataset(self, sample_json, capsys):
        """Records-shaped JSON has no sheet structure: one bare line."""
        rc = cli(["--list-sheets", str(sample_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert out == "2 rows x 3 cols\n"

    def test_empty_workbook_prints_nothing(self, empty_workbook, capsys):
        rc = cli(["--list-sheets", str(empty_workbook)])
        out = capsys.readouterr().out
        assert rc == 0
        assert out == ""

    def test_unknown_format_exits(self, tmp_path):
        bogus = tmp_path / "mystery.xyz"
        bogus.write_bytes(b"\x00\x01\x02not-a-known-format")
        with pytest.raises(SystemExit):
            cli(["--list-sheets", str(bogus)])

    def test_combined_with_output_rejected(self, sample_csv, tmp_path):
        out = tmp_path / "out.xlsx"
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", "-o", str(out), str(sample_csv)])

    def test_combined_with_format_rejected(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", "-t", "csv", str(sample_csv)])

    def test_combined_with_list_formats_rejected(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", "--list-formats", str(sample_csv)])

    def test_no_input_rejected(self):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets"], stdin_isatty=True)

    def test_two_inputs_rejected(self, sample_csv, sample_json):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", str(sample_csv), str(sample_json)])


# --- -s/--sheet ---


class TestSheetSelect:
    # argparse level: token cooking and rejections

    def test_occurrences_append(self, multi_sheet_xlsx):
        args, _ = parse_command_line(
            ["-s", "Users", "-s", "cities", str(multi_sheet_xlsx)]
        )
        assert args.sheets == ["Users", "cities"]

    def test_comma_split_when_all_ints(self, multi_sheet_xlsx):
        args, _ = parse_command_line(["-s", " 0 , 2 ", str(multi_sheet_xlsx)])
        assert args.sheets == ["0", "2"]

    def test_mixed_comma_stays_literal(self, multi_sheet_xlsx):
        args, _ = parse_command_line(["-s", "0,Users", str(multi_sheet_xlsx)])
        assert args.sheets == ["0,Users"]

    def test_title_with_comma_stays_whole(self, multi_sheet_xlsx):
        args, _ = parse_command_line(["-s", "Revenue, EMEA", str(multi_sheet_xlsx)])
        assert args.sheets == ["Revenue, EMEA"]

    @pytest.mark.parametrize("selector", ["", ",", "0,", " , "])
    def test_empty_selector_rejected(self, multi_sheet_xlsx, selector):
        with pytest.raises(SystemExit):
            parse_command_line(["-s", selector, str(multi_sheet_xlsx)])

    def test_combined_with_all_sheets_rejected(self, multi_sheet_xlsx):
        with pytest.raises(SystemExit):
            parse_command_line(["-s", "0", "--all-sheets", str(multi_sheet_xlsx)])

    def test_combined_with_list_sheets_rejected(self, multi_sheet_xlsx):
        with pytest.raises(SystemExit):
            parse_command_line(["-s", "0", "--list-sheets", str(multi_sheet_xlsx)])

    def test_combined_with_list_formats_rejected(self):
        with pytest.raises(SystemExit):
            parse_command_line(["-s", "0", "--list-formats"])

    def test_stdin_explicit_rejected(self):
        with pytest.raises(SystemExit):
            parse_command_line(["-s", "0", "-"])

    def test_stdin_implicit_rejected(self):
        with pytest.raises(SystemExit):
            parse_command_line(["-s", "0"], stdin_isatty=False)

    def test_no_input_rejected(self):
        with pytest.raises(SystemExit):
            parse_command_line(["-s", "0"], stdin_isatty=True)

    def test_multiple_inputs_rejected(self, sample_csv, sample_json, tmp_path):
        out = tmp_path / "out.xlsx"
        with pytest.raises(SystemExit):
            parse_command_line(
                ["-s", "0", "-o", str(out), str(sample_csv), str(sample_json)]
            )

    # cli level: resolution

    def test_pick_by_index(self, multi_sheet_xlsx, capsys):
        rc = cli(["-s", "1", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Stockholm" in out
        assert "Alice" not in out
        assert "===" not in out

    def test_pick_by_title(self, multi_sheet_xlsx, capsys):
        rc = cli(["-s", "people", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Alice" in out
        assert "===" not in out

    def test_pick_by_case_insensitive_title(self, multi_sheet_xlsx, capsys):
        rc = cli(["-s", "PEOPLE", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Alice" in out

    def test_year_index_out_of_range_hints_name(self, year_title_json):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "2024", str(year_title_json)])
        msg = str(excinfo.value)
        assert "sheet index 2024 out of range (0-0)" in msg
        assert "--sheet name:2024" in msg

    def test_name_prefix_forces_title(self, year_title_json, capsys):
        rc = cli(["-s", "name:2024", str(year_title_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Jan" in out

    def test_out_of_range_without_matching_title(self, multi_sheet_xlsx):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "9", str(multi_sheet_xlsx)])
        msg = str(excinfo.value)
        assert "sheet index 9 out of range (0-1)" in msg
        assert "name:" not in msg

    def test_doubled_name_prefix_escapes_literal(self, tmp_path, capsys):
        book = [{"title": "name:2024", "data": [{"month": "Jan"}]}]
        p = tmp_path / "odd.json"
        p.write_text(json.dumps(book))
        rc = cli(["-s", "name:name:2024", str(p)])
        assert rc == 0
        assert "Jan" in capsys.readouterr().out

    def test_duplicate_titles_ambiguous(self, dup_title_json):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "Users", str(dup_title_json)])
        msg = str(excinfo.value)
        assert "ambiguous" in msg
        assert "[0]" in msg
        assert "[2]" in msg

    def test_case_insensitive_ambiguous(self, case_dup_json):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "Users", str(case_dup_json)])
        assert "ambiguous" in str(excinfo.value)

    def test_exact_match_beats_case_insensitive(self, case_dup_json, capsys):
        rc = cli(["-s", "users", str(case_dup_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Alice" in out
        assert "Bob" not in out

    def test_unknown_title_lists_titles(self, multi_sheet_xlsx):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "nope", str(multi_sheet_xlsx)])
        msg = str(excinfo.value)
        assert "no sheet titled 'nope'" in msg
        assert "'people'" in msg
        assert "'cities'" in msg
        assert "repeat --sheet" not in msg

    def test_comma_miss_adds_repeat_hint(self, multi_sheet_xlsx):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "0,people", str(multi_sheet_xlsx)])
        msg = str(excinfo.value)
        assert "no sheet titled '0,people'" in msg
        assert "repeat --sheet to select multiple sheets by name" in msg

    def test_empty_workbook_errors(self, empty_workbook):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "0", str(empty_workbook)])
        assert "workbook has no sheets" in str(excinfo.value)

    def test_empty_title_selectable_by_index_only(self, empty_title_json, capsys):
        rc = cli(["-s", "0", str(empty_title_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Alice" in out

    def test_empty_title_skipped_in_title_match(self, empty_title_json, capsys):
        rc = cli(["-s", "named", str(empty_title_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Bob" in out

    @pytest.mark.parametrize("fixture", ["sample_csv", "sample_json"])
    def test_no_sheet_structure_rejected(self, fixture, request):
        path = request.getfixturevalue(fixture)
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "0", str(path)])
        assert "input has no sheet structure" in str(excinfo.value)

    def test_one_sheet_workbook_selectable_by_index(self, one_sheet_xlsx, capsys):
        rc = cli(["-s", "0", str(one_sheet_xlsx)])
        assert rc == 0
        assert "Alice" in capsys.readouterr().out

    def test_one_sheet_workbook_selectable_by_title(self, one_sheet_xlsx, capsys):
        rc = cli(["-s", "people", str(one_sheet_xlsx)])
        assert rc == 0
        assert "Alice" in capsys.readouterr().out

    # cli level: rendering

    def test_multi_select_print_layout(self, multi_sheet_json, capsys):
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

    def test_selection_order_preserved(self, multi_sheet_json, capsys):
        rc = cli(["-s", "2,0", str(multi_sheet_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert out.index("=== products") < out.index("=== people")

    def test_duplicates_deduped(self, multi_sheet_json, capsys):
        rc = cli(["-s", "0,1,0", str(multi_sheet_json)])
        out = capsys.readouterr().out
        assert rc == 0
        headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
        assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]

    def test_dedup_to_single_renders_plain(self, multi_sheet_json, capsys):
        rc = cli(["-s", "0,0", str(multi_sheet_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "===" not in out
        assert "Alice" in out

    def test_repeat_flag_mixes_title_and_index(self, multi_sheet_json, capsys):
        rc = cli(["-s", "people", "-s", "1", str(multi_sheet_json)])
        out = capsys.readouterr().out
        assert rc == 0
        headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
        assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]

    def test_single_select_save(self, multi_sheet_xlsx, tmp_path):
        out_file = tmp_path / "cities.csv"
        rc = cli(["-s", "cities", "-o", str(out_file), str(multi_sheet_xlsx)])
        assert rc == 0
        assert "Stockholm" in out_file.read_text()

    def test_single_select_export(self, multi_sheet_xlsx, capsys):
        rc = cli(["-s", "0", "-t", "json", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        rows = json.loads(out)
        assert rows[0]["name"] == "Alice"

    def test_multi_select_export_json(self, multi_sheet_json, capsys):
        rc = cli(["-s", "0,1", "-t", "json", str(multi_sheet_json)])
        out = capsys.readouterr().out
        assert rc == 0
        book = json.loads(out)
        assert [sheet["title"] for sheet in book] == ["people", "cities"]

    def test_multi_select_save_roundtrip(self, multi_sheet_json, tmp_path):
        out_file = tmp_path / "subset.xlsx"
        rc = cli(["-s", "2,0", "-o", str(out_file), str(multi_sheet_json)])
        assert rc == 0
        loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
        assert [s.title for s in loaded.sheets()] == ["products", "people"]

    def test_multi_select_save_unsupported_hints_sheet(
        self, multi_sheet_json, tmp_path
    ):
        out_file = tmp_path / "subset.csv"
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "0,1", "-o", str(out_file), str(multi_sheet_json)])
        msg = str(excinfo.value)
        assert "does not support multi-sheet output" in msg
        assert "pick one sheet with --sheet" in msg

    def test_multi_select_export_unsupported_hints_sheet(self, multi_sheet_json):
        with pytest.raises(SystemExit) as excinfo:
            cli(["-s", "0,1", "-t", "csv", str(multi_sheet_json)])
        msg = str(excinfo.value)
        assert "does not support multi-sheet output" in msg
        assert "pick one sheet with --sheet" in msg

    def test_tablefmt_applies_to_multi_print(self, multi_sheet_json, capsys):
        rc = cli(["-s", "0,1", "--tablefmt", "grid", str(multi_sheet_json)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "+" in out

    def test_tablefmt_applies_to_single_print(self, sample_csv, capsys):
        rc = cli(["--tablefmt", "grid", str(sample_csv)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "+---" in out


# --- --all-sheets ---


class TestAllSheets:
    def test_print_all(self, multi_sheet_xlsx, capsys):
        rc = cli(["--all-sheets", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        headings = [ln for ln in out.splitlines() if ln.startswith("=== ")]
        assert headings == ["=== people (2 rows) ===", "=== cities (2 rows) ==="]

    def test_save_roundtrip(self, multi_sheet_xlsx, tmp_path):
        out_file = tmp_path / "all.xlsx"
        rc = cli(["--all-sheets", "-o", str(out_file), str(multi_sheet_xlsx)])
        assert rc == 0
        loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
        assert loaded.size == 2

    def test_save_unsupported_hints_sheet(self, multi_sheet_xlsx, tmp_path):
        out_file = tmp_path / "all.csv"
        with pytest.raises(SystemExit) as excinfo:
            cli(["--all-sheets", "-o", str(out_file), str(multi_sheet_xlsx)])
        msg = str(excinfo.value)
        assert "does not support multi-sheet output" in msg
        assert "pick one sheet with --sheet" in msg

    def test_export_json(self, multi_sheet_xlsx, capsys):
        rc = cli(["--all-sheets", "-t", "json", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        book = json.loads(out)
        assert [sheet["title"] for sheet in book] == ["people", "cities"]

    def test_identity_on_csv_print(self, sample_csv, capsys):
        rc = cli(["--all-sheets", str(sample_csv)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "===" not in out
        assert "Alice" in out

    def test_identity_on_csv_export(self, sample_csv, capsys):
        rc = cli(["--all-sheets", "-t", "json", str(sample_csv)])
        out = capsys.readouterr().out
        assert rc == 0
        rows = json.loads(out)
        assert rows[0]["name"] == "Alice"

    def test_one_sheet_workbook_single_render(self, one_sheet_xlsx, capsys):
        rc = cli(["--all-sheets", str(one_sheet_xlsx)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "===" not in out
        assert "Alice" in out

    def test_empty_workbook_errors(self, empty_workbook):
        with pytest.raises(SystemExit) as excinfo:
            cli(["--all-sheets", str(empty_workbook)])
        assert "workbook has no sheets" in str(excinfo.value)

    def test_combined_with_list_sheets_rejected(self, multi_sheet_xlsx):
        with pytest.raises(SystemExit):
            parse_command_line(["--all-sheets", "--list-sheets", str(multi_sheet_xlsx)])

    def test_combined_with_list_formats_rejected(self):
        with pytest.raises(SystemExit):
            parse_command_line(["--all-sheets", "--list-formats"])

    def test_stdin_rejected(self):
        with pytest.raises(SystemExit):
            parse_command_line(["--all-sheets", "-"])

    def test_multiple_inputs_rejected(self, sample_csv, sample_json, tmp_path):
        out = tmp_path / "out.xlsx"
        with pytest.raises(SystemExit):
            parse_command_line(
                ["--all-sheets", "-o", str(out), str(sample_csv), str(sample_json)]
            )


# --- default mode on a multi-sheet input ---


class TestDefaultMultiSheet:
    """Default mode: whole-book conversion, first-sheet print, no silent loss."""

    # --- terminal print + advice ---

    def test_print_shows_first_sheet_only(self, multi_sheet_xlsx, capsys):
        rc = cli([str(multi_sheet_xlsx)], stderr_isatty=False)
        out = capsys.readouterr().out
        assert rc == 0
        assert "Alice" in out
        assert "Stockholm" not in out
        assert "===" not in out

    def test_advice_on_tty(self, multi_sheet_xlsx, capsys):
        cli([str(multi_sheet_xlsx)], stderr_isatty=True)
        err = capsys.readouterr().err
        assert f"{multi_sheet_xlsx}: 1 more sheet(s)" in err
        assert "-l to list" in err
        assert "-s to pick" in err
        assert "--all-sheets for all" in err

    def test_no_advice_when_piped(self, multi_sheet_xlsx, capsys):
        """Advice is for a watching human; in a pipe it is only noise."""
        cli([str(multi_sheet_xlsx)], stderr_isatty=False)
        assert capsys.readouterr().err == ""

    def test_advice_counts_remaining_sheets(self, multi_sheet_json, capsys):
        cli([str(multi_sheet_json)], stderr_isatty=True)
        assert "2 more sheet(s)" in capsys.readouterr().err

    def test_stdout_identical_regardless_of_tty(self, multi_sheet_xlsx, capsys):
        """The gate must affect stderr only."""
        cli([str(multi_sheet_xlsx)], stderr_isatty=True)
        on_tty = capsys.readouterr().out
        cli([str(multi_sheet_xlsx)], stderr_isatty=False)
        assert capsys.readouterr().out == on_tty

    def test_no_advice_for_one_sheet_workbook(self, one_sheet_xlsx, capsys):
        rc = cli([str(one_sheet_xlsx)], stderr_isatty=True)
        captured = capsys.readouterr()
        assert rc == 0
        assert "Alice" in captured.out
        assert captured.err == ""

    @pytest.mark.parametrize("fixture", ["sample_csv", "sample_json"])
    def test_no_advice_for_structureless_input(self, fixture, request, capsys):
        path = request.getfixturevalue(fixture)
        rc = cli([str(path)], stderr_isatty=True)
        captured = capsys.readouterr()
        assert rc == 0
        assert "Alice" in captured.out
        assert captured.err == ""

    @pytest.mark.parametrize("flags", [["-s", "0"], ["--all-sheets"]])
    def test_no_advice_with_selection_flags(self, flags, multi_sheet_xlsx, capsys):
        """Selection takes another dispatch path, so the advice is suppressed."""
        rc = cli([*flags, str(multi_sheet_xlsx)], stderr_isatty=True)
        assert rc == 0
        assert capsys.readouterr().err == ""

    def test_no_advice_with_list_sheets(self, multi_sheet_xlsx, capsys):
        rc = cli(["-l", str(multi_sheet_xlsx)], stderr_isatty=True)
        captured = capsys.readouterr()
        assert rc == 0
        assert "[0] people" in captured.out
        assert captured.err == ""

    # --- whole-book conversion ---

    def test_save_keeps_all_sheets(self, multi_sheet_json, tmp_path, capsys):
        out_file = tmp_path / "out.xlsx"
        rc = cli(["-o", str(out_file), str(multi_sheet_json)], stderr_isatty=True)
        captured = capsys.readouterr()
        assert rc == 0
        loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
        assert loaded.size == 3
        assert "3 sheets" in captured.out
        assert captured.err == ""

    def test_export_keeps_all_sheets(self, multi_sheet_xlsx, capsys):
        rc = cli(["-t", "json", str(multi_sheet_xlsx)], stderr_isatty=False)
        captured = capsys.readouterr()
        assert rc == 0
        book = json.loads(captured.out)
        assert [sheet["title"] for sheet in book] == ["people", "cities"]
        assert captured.err == ""

    def test_save_json_uses_book_shape(self, multi_sheet_xlsx, tmp_path):
        out_file = tmp_path / "out.json"
        cli(["-o", str(out_file), str(multi_sheet_xlsx)], stderr_isatty=False)
        book = json.loads(out_file.read_text())
        assert [sheet["title"] for sheet in book] == ["people", "cities"]

    def test_positional_outfile_keeps_all_sheets(self, multi_sheet_xlsx, tmp_path):
        """The two-positional style is the same conversion path as -o."""
        out_file = tmp_path / "out.xlsx"
        rc = cli([str(multi_sheet_xlsx), str(out_file)], stderr_isatty=False)
        assert rc == 0
        loaded = tablib.Databook().load(out_file.read_bytes(), format="xlsx")
        assert loaded.size == 2

    # --- fallback + unconditional data-loss warning ---

    @pytest.mark.parametrize("isatty", [True, False])
    def test_export_csv_falls_back_with_warning(self, isatty, multi_sheet_xlsx, capsys):
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

    def test_fallback_never_suggests_all_sheets(self, multi_sheet_xlsx, capsys):
        """--all-sheets errors in this same situation, so it must not be advised."""
        cli(["-t", "csv", str(multi_sheet_xlsx)], stderr_isatty=True)
        assert "--all-sheets" not in capsys.readouterr().err

    def test_save_csv_falls_back_cleanly(self, multi_sheet_xlsx, tmp_path, capsys):
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

    def test_fallback_names_the_attempted_format(
        self, multi_sheet_xlsx, tmp_path, capsys
    ):
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

    def test_fallback_to_cli_matches_bare_print(self, multi_sheet_xlsx, capsys):
        """Stdout stays identical; only stderr distinguishes view from conversion."""
        cli([str(multi_sheet_xlsx)], stderr_isatty=True)
        printed = capsys.readouterr()
        cli(["-t", "cli", str(multi_sheet_xlsx)], stderr_isatty=True)
        exported = capsys.readouterr()
        assert exported.out == printed.out
        assert "more sheet(s)" in printed.err
        assert "cannot hold all" in exported.err

    # --- unrelated errors are not swallowed ---

    def test_undetectable_target_format_not_swallowed(
        self, multi_sheet_xlsx, tmp_path, capsys
    ):
        out_file = tmp_path / "out.zzz"
        with pytest.raises(SystemExit) as excinfo:
            cli(["-o", str(out_file), str(multi_sheet_xlsx)], stderr_isatty=False)
        msg = str(excinfo.value)
        assert "Unable to detect target file format" in msg
        assert "cannot hold" not in msg
        assert "cannot hold" not in capsys.readouterr().err
        assert not out_file.exists()

    def test_all_sheets_still_errors_where_default_falls_back(
        self, multi_sheet_xlsx, tmp_path
    ):
        """Explicit flags stay strict; only the default is best-effort."""
        out_file = tmp_path / "out.csv"
        with pytest.raises(SystemExit) as excinfo:
            cli(["--all-sheets", "-o", str(out_file), str(multi_sheet_xlsx)])
        assert "pick one sheet with --sheet" in str(excinfo.value)

    # --- degenerate inputs ---

    def test_empty_workbook_names_the_source(self, empty_workbook):
        """The default path names the file it read; selection reports structure."""
        with pytest.raises(SystemExit) as excinfo:
            cli([str(empty_workbook)], stderr_isatty=False)
        assert f"No data was loaded from {empty_workbook}" in str(excinfo.value)

    def test_one_sheet_json_book_renders_its_sheet(self, year_title_json, capsys):
        """Previously this printed a bogus two-column title/data table."""
        rc = cli([str(year_title_json)], stderr_isatty=True)
        captured = capsys.readouterr()
        assert rc == 0
        assert "month" in captured.out
        assert "Jan" in captured.out
        assert "data" not in captured.out
        assert captured.err == ""

    def test_headers_only_csv_still_reports_no_data(self, tmp_path):
        p = tmp_path / "hdr.csv"
        p.write_text("a,b\n")
        with pytest.raises(SystemExit) as excinfo:
            cli([str(p)], stderr_isatty=False)
        assert f"No data was loaded from {p}" in str(excinfo.value)

    def test_empty_first_sheet_advises_without_error(self, tmp_path, capsys):
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

    # --- stdin reads exactly like a file argument ---

    def test_stdin_multi_sheet_keeps_all_sheets(self, multi_sheet_xlsx, capsys):
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

    def test_stdin_multi_sheet_fallback_warns(self, multi_sheet_xlsx, capsys):
        rc = cli(
            ["-", "-f", "xlsx", "-t", "csv"],
            stdin=io.BytesIO(multi_sheet_xlsx.read_bytes()),
            stderr_isatty=False,
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert "stdin: format 'csv' cannot hold all 2 sheets" in captured.err
        assert captured.out.startswith("name,age")

    def test_stdin_csv_unchanged(self, capsys):
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


class TestPrintRendering:
    def test_default_print_matches_t_cli(self, sample_csv, capsys):
        cli([str(sample_csv)])
        printed = capsys.readouterr().out
        cli(["-t", "cli", str(sample_csv)])
        exported = capsys.readouterr().out
        assert printed == exported

    def test_default_print_matches_t_cli_with_tablefmt(self, sample_csv, capsys):
        cli(["--tablefmt", "grid", str(sample_csv)])
        printed = capsys.readouterr().out
        cli(["--tablefmt", "grid", "-t", "cli", str(sample_csv)])
        exported = capsys.readouterr().out
        assert printed == exported
        assert "+---" in printed

    def test_default_style_is_tabulate_plain(self, sample_csv, capsys):
        """Not tablib's __str__ table: no pipe separators, no dashed rule."""
        cli([str(sample_csv)])
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "|" not in out
        assert "---" not in out

    @pytest.mark.parametrize("fmt", ["cli", "json"])
    def test_text_export_to_stdout_ends_with_one_newline(self, sample_csv, capsys, fmt):
        cli(["-t", fmt, str(sample_csv)])
        out = capsys.readouterr().out
        assert out.endswith("\n")
        assert not out.endswith("\n\n")

    def test_saved_file_has_no_added_newline(self, sample_csv, tmp_path):
        """The newline is a stdout courtesy; -o writes the payload verbatim."""
        out_file = tmp_path / "out.json"
        cli(["-o", str(out_file), str(sample_csv)])
        assert not out_file.read_text().endswith("\n")

    def test_falls_back_to_builtin_table_without_cli_format(
        self, sample_csv, capsys, monkeypatch
    ):
        _without_cli_format(monkeypatch)
        cli([str(sample_csv)])
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "|" in out  # tablib's own __str__ joins columns with pipes

    def test_multi_sheet_print_falls_back_too(
        self, multi_sheet_xlsx, capsys, monkeypatch
    ):
        _without_cli_format(monkeypatch)
        cli(["--all-sheets", str(multi_sheet_xlsx)])
        out = capsys.readouterr().out
        assert "=== people (2 rows) ===" in out
        assert "|" in out
