"""Tests for tublub.main."""

import io
import sys
from pathlib import Path

import pytest

from tublub.main import (
    BINARY_FORMATS,
    LOAD_EXTRA_ARGS,
    SAVE_EXTRA_ARGS,
    TublubError,
    build_argument_parser,
    export_dataset,
    filter_args,
    get_formats,
    guess_file_format,
    is_bin,
    load_dataset_file,
    load_dataset_stdin,
    parse_command_line,
    save_dataset_file,
)

# --- guess_file_format ---


class TestGuessFileFormat:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [("data.csv", "csv"), ("data.json", "json"), ("data.xlsx", "xlsx"),
         ("report.yaml", "yaml"), ("data.tsv", "tsv")],
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
    @pytest.mark.parametrize("fmt", sorted(BINARY_FORMATS))
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
        result = filter_args(LOAD_EXTRA_ARGS, user_args, "csv")
        assert result == {"skip_lines": 2, "delimiter": ","}

    def test_excludes_irrelevant_args(self):
        user_args = {"skip_lines": 2, "delimiter": ","}
        result = filter_args(LOAD_EXTRA_ARGS, user_args, "xlsx")
        assert result == {"skip_lines": 2}
        assert "delimiter" not in result

    def test_unknown_format_returns_empty(self):
        user_args = {"skip_lines": 2}
        result = filter_args(LOAD_EXTRA_ARGS, user_args, "json")
        assert result == {}

    def test_none_values_excluded(self):
        user_args = {"skip_lines": None, "delimiter": ","}
        result = filter_args(LOAD_EXTRA_ARGS, user_args, "csv")
        assert result == {"delimiter": ","}

    def test_empty_user_args(self):
        result = filter_args(LOAD_EXTRA_ARGS, {}, "csv")
        assert result == {}

    def test_save_extra_args(self):
        user_args = {"tablefmt": "fancy_grid"}
        result = filter_args(SAVE_EXTRA_ARGS, user_args, "cli")
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


# --- load_dataset_file ---


class TestLoadDatasetFile:
    @pytest.mark.parametrize(
        "fixture", ["sample_csv", "sample_json", "sample_tsv", "sample_yaml"],
    )
    def test_load_formats(self, fixture, request):
        path = request.getfixturevalue(fixture)
        ds = load_dataset_file(path, extra_args={})
        assert len(ds) == 2
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
        assert args.infile == sample_csv
        assert args.outfile is None

    def test_infile_and_outfile(self, sample_csv, tmp_path):
        out = tmp_path / "out.json"
        args, extra = parse_command_line([str(sample_csv), str(out)])
        assert args.infile == sample_csv
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
        assert args.infile is None

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
