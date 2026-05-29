"""Tests for tublub.main."""

import io
import sys
from pathlib import Path

import pytest
import tablib

from tublub.main import (
    FORMATS,
    TublubError,
    _looks_like_text_lines,
    _unique_titles,
    build_argument_parser,
    build_databook,
    cli,
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

    def test_export_binary_to_tty_raises(self, sample_data, monkeypatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        with pytest.raises(TublubError, match="binary"):
            export_dataset(sample_data, "xlsx", extra_args={})

    def test_export_binary_to_piped_stdout(self, sample_data, monkeypatch):
        """Binary export to non-TTY stdout should use stdout.buffer."""
        chunks = []
        fake_buffer = type("buf", (), {"write": lambda self, d: chunks.append(d)})()
        fake_stdout = type(
            "fake_stdout", (), {"isatty": lambda self: False, "buffer": fake_buffer}
        )()
        monkeypatch.setattr(sys, "stdout", fake_stdout)
        export_dataset(sample_data, "xlsx", extra_args={})
        assert len(chunks) == 1
        assert isinstance(chunks[0], bytes)

    def test_export_text_to_non_tty(self, sample_data, tmp_path):
        out = tmp_path / "piped.json"
        with out.open("w") as fh:
            export_dataset(sample_data, "json", extra_args={}, file_handle=fh)
        assert "Alice" in out.read_text()


# --- parse_command_line ---


class TestParseCommandLine:
    def test_list_flag(self):
        args, extra = parse_command_line(["--list"])
        assert args.list is True

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

    def test_no_input_exits(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        with pytest.raises(SystemExit):
            parse_command_line([])

    def test_nonexistent_file_exits(self):
        with pytest.raises(SystemExit):
            parse_command_line(["/no/such/file.csv"])

    def test_invalid_format_exits(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["-t", "bogus", str(sample_csv)])

    def test_list_with_file_exits(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["--list", str(sample_csv)])

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
    def test_auto_detect(self, monkeypatch, sample_data, fmt):
        raw = sample_data.export(fmt)
        if isinstance(raw, str):
            raw = raw.encode()
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
        ds = load_dataset_stdin()
        assert len(ds) == 2
        assert ds.headers is not None
        assert "name" in ds.headers

    def test_explicit_format(self, monkeypatch):
        csv_bytes = b"name,age\nAlice,30\n"
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(csv_bytes)))
        ds = load_dataset_stdin(in_format="csv")
        assert len(ds) == 1

    def test_extra_args_passed(self, monkeypatch):
        csv_bytes = b"# comment\nname,age\nAlice,30\n"
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(csv_bytes)))
        ds = load_dataset_stdin(in_format="csv", extra_args={"skip_lines": 1})
        assert len(ds) == 1
        assert ds.headers == ["name", "age"]

    def test_empty_stdin_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))
        with pytest.raises(TublubError, match="No data received"):
            load_dataset_stdin()

    def test_single_column_heuristic(self, monkeypatch):
        """Single-column data on stdin should be detected as TSV via heuristic."""
        raw = b"name\nAlice\nBob\n"
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
        ds = load_dataset_stdin()
        assert len(ds) == 2
        assert ds.headers == ["name"]

    def test_undetectable_format_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"???")))
        with pytest.raises(TublubError, match=r"Unable to detect.*-f"):
            load_dataset_stdin()


# --- parse_command_line stdin ---


class TestParseCommandLineStdin:
    def test_dash_sets_stdin_flag(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        args, _ = parse_command_line(["-", "-t", "json"])
        assert args.stdin is True
        assert args.infiles == []

    def test_implicit_stdin_when_piped(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        args, _ = parse_command_line(["-t", "json"])
        assert args.stdin is True

    def test_in_format_flag(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        args, _ = parse_command_line(["-f", "csv", "-t", "json"])
        assert args.in_format == "csv"

    def test_invalid_in_format_exits(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        with pytest.raises(SystemExit):
            parse_command_line(["-f", "bogus", "-t", "json"])

    def test_in_format_with_file(self, sample_csv):
        args, _ = parse_command_line(["-f", "csv", str(sample_csv)])
        assert args.in_format == "csv"
        assert args.stdin is False


# --- _unique_titles ---


class TestUniqueTitles:
    def test_distinct_stems(self):
        paths = [Path("a.csv"), Path("b.json"), Path("c.tsv")]
        assert _unique_titles(paths) == ["a", "b", "c"]

    def test_collision_uses_parent(self, capsys):
        paths = [Path("d1/sales.csv"), Path("d2/sales.csv")]
        assert _unique_titles(paths) == ["d1_sales", "d2_sales"]
        assert "disambiguated" in capsys.readouterr().err

    def test_triple_collision_uses_parent(self):
        paths = [Path("a/x.csv"), Path("b/x.csv"), Path("c/x.csv")]
        assert _unique_titles(paths) == ["a_x", "b_x", "c_x"]

    def test_mixed_collisions(self):
        paths = [
            Path("a/sales.csv"),
            Path("users.json"),
            Path("b/sales.csv"),
            Path("c/sales.csv"),
        ]
        assert _unique_titles(paths) == [
            "a_sales",
            "users",
            "b_sales",
            "c_sales",
        ]

    def test_parent_collision_falls_back_to_numeric_suffix(self):
        # Two inputs share both parent name AND stem → parent_stem still
        # collides, so the _2 suffix kicks in.
        paths = [Path("proj_a/data/x.csv"), Path("proj_b/data/x.csv")]
        assert _unique_titles(paths) == ["data_x", "data_x_2"]

    def test_bare_filename_falls_back_to_numeric_suffix(self, capsys):
        # No parent name available for "Sales.csv" → numeric suffix.
        paths = [Path("Sales.csv"), Path("dir/Sales.csv")]
        assert _unique_titles(paths) == ["Sales", "dir_Sales"]
        assert "disambiguated" in capsys.readouterr().err

    def test_no_collision_no_note(self, capsys):
        paths = [Path("a.csv"), Path("b.csv")]
        _unique_titles(paths)
        assert capsys.readouterr().err == ""

    def test_empty(self):
        assert _unique_titles([]) == []

    def test_long_stem_truncated_to_limit(self, capsys):
        stem = "a" * 40
        titles = _unique_titles([Path(f"{stem}.csv")])
        assert titles == ["a" * 31]
        assert all(len(t) <= 31 for t in titles)
        assert "disambiguated" in capsys.readouterr().err

    def test_long_shared_prefix_stays_unique(self):
        # Two distinct stems sharing a >31-char prefix clamp to the same 31
        # chars, so the _2 suffix kicks in with the base trimmed to fit.
        prefix = "x" * 40
        titles = _unique_titles([Path(f"{prefix}A.csv"), Path(f"{prefix}B.csv")])
        assert all(len(t) <= 31 for t in titles)
        assert len(set(titles)) == 2
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
    def test_multi_sheet_xlsx_from_stdin(self, multi_sheet_xlsx, monkeypatch):
        monkeypatch.setattr(
            sys, "stdin", io.TextIOWrapper(io.BytesIO(multi_sheet_xlsx.read_bytes()))
        )
        book = load_databook_stdin()
        assert book is not None
        assert book.size == 2

    def test_csv_from_stdin_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "stdin",
            io.TextIOWrapper(io.BytesIO(b"name,age\nAlice,30\nBob,25\n")),
        )
        assert load_databook_stdin() is None

    def test_empty_stdin_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))
        with pytest.raises(TublubError, match="No data"):
            load_databook_stdin()


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

    def test_o_with_no_inputs_and_tty_exits(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        out = tmp_path / "out.json"
        with pytest.raises(SystemExit):
            parse_command_line(["-o", str(out)])

    def test_nonexistent_input_in_multi_exits(self, sample_csv, tmp_path):
        out = tmp_path / "book.xlsx"
        with pytest.raises(SystemExit):
            parse_command_line(["-o", str(out), str(sample_csv), "/no/such/file.csv"])


# --- cli() integration: multi-input → Databook ---


class TestCliDatabook:
    def test_multi_input_to_xlsx(self, sample_csv, sample_json, tmp_path, monkeypatch):
        out = tmp_path / "book.xlsx"
        monkeypatch.setattr(
            sys, "argv", ["tublub", "-o", str(out), str(sample_csv), str(sample_json)]
        )
        rc = cli()
        assert rc == 0
        loaded = tablib.Databook().load(out.read_bytes(), format="xlsx")
        assert loaded.size == 2

    def test_unsupported_output_exits(self, sample_csv, tmp_path, monkeypatch):
        out = tmp_path / "book.csv"
        monkeypatch.setattr(
            sys, "argv", ["tublub", "-o", str(out), str(sample_csv), str(sample_csv)]
        )
        with pytest.raises(SystemExit):
            cli()


# --- --list-sheets ---


class TestListSheets:
    def test_argparse_flag(self, sample_csv):
        args, _ = parse_command_line(["--list-sheets", str(sample_csv)])
        assert args.list_sheets is True

    def test_xlsx_lists_all_sheets(self, multi_sheet_xlsx, capsys, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["tublub", "--list-sheets", str(multi_sheet_xlsx)]
        )
        rc = cli()
        out = capsys.readouterr().out
        assert rc == 0
        lines = out.strip().splitlines()
        assert len(lines) == 2
        assert lines[0] == "[0] people  2 rows x 2 cols"
        assert lines[1] == "[1] cities  2 rows x 2 cols"

    def test_csv_falls_back_to_dataset(self, sample_csv, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["tublub", "--list-sheets", str(sample_csv)])
        rc = cli()
        out = capsys.readouterr().out
        assert rc == 0
        lines = out.strip().splitlines()
        assert len(lines) == 1
        assert lines[0] == f"[0] {sample_csv.stem}  2 rows x 3 cols"

    def test_unknown_format_exits(self, tmp_path, monkeypatch):
        bogus = tmp_path / "mystery.xyz"
        bogus.write_bytes(b"\x00\x01\x02not-a-known-format")
        monkeypatch.setattr(sys, "argv", ["tublub", "--list-sheets", str(bogus)])
        with pytest.raises(SystemExit):
            cli()

    def test_combined_with_output_rejected(self, sample_csv, tmp_path):
        out = tmp_path / "out.xlsx"
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", "-o", str(out), str(sample_csv)])

    def test_combined_with_format_rejected(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", "-t", "csv", str(sample_csv)])

    def test_combined_with_list_rejected(self, sample_csv):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", "--list", str(sample_csv)])

    def test_no_input_rejected(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets"])

    def test_two_inputs_rejected(self, sample_csv, sample_json):
        with pytest.raises(SystemExit):
            parse_command_line(["--list-sheets", str(sample_csv), str(sample_json)])
