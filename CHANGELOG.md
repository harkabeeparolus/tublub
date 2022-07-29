# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com),
and this project adheres to [Semantic Versioning](https://semver.org).

## [Unreleased]

Nothing yet.

## [0.3.0] - 2022-07-29

### Added

* Extra format detection with Tablib before loading file.

### Changed

* Added *headers* for TSV format as well as CSV.
* Improved console handling for printing to stdout.

### Removed

* Pandas is no longer included, since DataFrames is not a file format.
  It also reduces the installation size on disk.

## [0.2.0] - 2022-07-29

### Added

* Warn and exit on empty input or missing input file.
* Added `--version` flag.

### Changed

* Better heuristics for guessing text or binary file format.
* Filter keyword arguments for `load()` to include only arguments that are valid
  for the current input format.

## [0.1.0] - 2022-07-28

* Initial working version.
* Not feature complete.
