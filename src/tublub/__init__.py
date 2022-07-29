import sys

# source: https://packaging.python.org/guides/single-sourcing-package-version/
if sys.version_info >= (3, 8):
    from importlib import metadata
else:
    import importlib_metadata as metadata

__version__ = metadata.version("tublub")
