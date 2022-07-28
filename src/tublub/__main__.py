"""Convert tabular information files between different formats using Tablib."""

import argparse
import functools
import sys
from pathlib import Path

import tablib
import tablib.formats
from tablib import Dataset

# https://tablib.readthedocs.io/en/stable/formats.html
BINARY_FORMATS = {"xlsx", "xls", "dbf", "ods"}


def main():
    """Run the command line interface."""
    args = parse_command_line()

    if args.list:
        print("Available formats:", " ".join(get_formats()))
        sys.exit()

    imported_data = load_dataset(args)
    target_format = detect_target_format(args)
    binary = target_format in BINARY_FORMATS

    if args.outfile:
        # Try to save to a file
        if target_format:
            with open(args.outfile, "wb" if binary else "w") as fh:
                fh.write(imported_data.export(target_format))
        else:
            sys.exit(f"Unable to detect target file format for: {args.outfile}")
    elif target_format:
        # Convert data to requested target format on stdout
        if binary and sys.stdout.isatty():
            sys.exit(f"Format {target_format} is binary, not printing to console!")
        print(imported_data.export(target_format))
    else:
        # Just print the tablib Dataset directly to stdout
        print(imported_data)


def detect_target_format(args):
    """Get target format from arguments or target file name."""
    target_format = args.out_format
    if args.outfile and not target_format:
        if (suf := Path(args.outfile).suffix.lstrip(".")) and suf in get_formats():
            target_format = suf
    return target_format


def load_dataset(args):
    """Load a file into a Tablib dataset."""
    imported_data = Dataset()
    if args.infile:
        try_binary = False
        with open(args.infile, "r") as fh:
            try:
                imported_data.load(fh, headers=args.headers)
            except TypeError:
                imported_data.load(fh)
            except UnicodeDecodeError:
                try_binary = True
        if try_binary:
            with open(args.infile, "rb") as fh:
                imported_data.load(fh)
    return imported_data


@functools.cache
def get_formats():
    """Get available Tablib formats."""
    return tuple(x.title for x in tablib.formats.registry.formats())


def parse_command_line():
    """Parse and return arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-l", "--list", action="store_true", help="List the available file formats."
    )
    parser.add_argument(
        "--no-headers",
        dest="headers",
        action="store_false",
        help="Use this option when your CSV/TSV input data has no header row.",
    )
    parser.add_argument(
        "-t", "--format", metavar="F", dest="out_format", help="Specify output format."
    )
    parser.add_argument("infile", nargs="?", help="input (source) file")
    parser.add_argument("outfile", nargs="?", help="output (destination) file")
    args = parser.parse_args()

    if args.list and (args.infile or args.outfile):
        parser.error("Can not combine --list with filename(s)")

    if args.out_format and args.out_format not in get_formats():
        parser.error(f"Invalid format {args.out_format}, use one of: {get_formats()}")

    return args


if __name__ == "__main__":
    main()
