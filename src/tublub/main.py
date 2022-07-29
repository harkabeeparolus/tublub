"""Convert tabular information files between different formats using Tablib.

If no outfile is specified the result will be printed instead, either in the
requested format, or pretty-printed as a table.
"""

import argparse
import functools
import sys
from collections import defaultdict
from pathlib import Path

import tablib
import tablib.formats

from tublub import __version__

# https://tablib.readthedocs.io/en/stable/formats.html
BINARY_FORMATS = {"xlsx", "xls", "dbf", "ods"}


def cli():
    """Run the command line interface."""
    args = parse_command_line()

    if args.list:
        print("Available formats:", " ".join(get_formats()))
        return

    my_data = load_dataset_file(args.infile, extra_args=args)
    if not my_data:
        sys.exit(f"No data was loaded from {args.infile}, exiting...")

    if args.outfile:
        save_dataset_file(my_data, file_name=args.outfile, force_format=args.out_format)
    elif args.out_format:
        export_dataset(my_data, args.out_format)
    else:
        print(my_data)


def guess_file_format(filename=None):
    """Guess format from file name."""
    if filename:
        if (suf := Path(filename).suffix.lstrip(".")) and suf in get_formats():
            return suf
    return None


def load_dataset_file(file_name, extra_args):
    """Load a file into a Tablib dataset."""
    input_format = guess_file_format(file_name)
    extra_load_args = extra_input_arguments(extra_args, input_format)

    with open(file_name, "rb" if is_bin(input_format) else "r") as fh:
        imported_data = tablib.import_set(fh, **extra_load_args)

    return imported_data


def save_dataset_file(data, file_name, force_format=None):
    """Save a Tablib dataset to a file."""
    file_format = force_format or guess_file_format(file_name)
    if not file_format:
        sys.exit(f"Unable to detect target file format for: {file_name}")

    with open(file_name, "wb" if is_bin(file_format) else "w") as fh:
        # fh.write(data.export(file_format))
        export_dataset(data, file_format, file_handle=fh)
    print(f"Saved '{file_name}', {len(data)} records ({file_format})")


def export_dataset(data, target_format, file_handle=sys.stdout):
    """Export dataset to a file handle or other stream."""
    if is_bin(target_format) and file_handle is sys.stdout and sys.stdout.isatty():
        sys.exit(f"Format {target_format} is binary, not printing to console!")

    file_handle.write(data.export(target_format))


def extra_input_arguments(args, file_format):
    """Create and select keyword arguments for Dataset().load(),
    filtered by input data format.
    """
    load_filter = defaultdict(set, {"csv": {"headers"}})
    all_args = {"headers": args.headers}
    return {k: v for k, v in all_args.items() if k in load_filter[file_format]}


@functools.cache
def get_formats():
    """Get a list of all available Tablib formats."""
    return tuple(x.title for x in tablib.formats.registry.formats())


def is_bin(data_format):
    """Return true if data format is binary."""
    return bool(data_format and data_format in BINARY_FORMATS)


def parse_command_line():
    """Parse and return command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List the available file formats and exit.",
    )
    parser.add_argument(
        "--no-headers",
        dest="headers",
        action="store_false",
        help="Use this option when your CSV/TSV input data has no header row.",
    )
    parser.add_argument(
        "-t",
        "--format",
        metavar="FORMAT",
        dest="out_format",
        help="Specify output format. Default: File extension from outfile, if provided.",
    )
    parser.add_argument("infile", nargs="?", help="input (source) file")
    parser.add_argument("outfile", nargs="?", help="output (destination) file")
    args = parser.parse_args()

    if args.list and (args.infile or args.outfile):
        parser.error("Can not combine --list with filename(s)")

    if not args.list and not args.infile:
        parser.error("No input data provided.")

    if args.infile and not Path(args.infile).is_file():
        parser.error(f"Input file {args.infile} does not exist.")

    if args.out_format and args.out_format not in get_formats():
        parser.error(f"Invalid format {args.out_format}, use one of: {get_formats()}")

    return args


if __name__ == "__main__":
    sys.exit(cli())
