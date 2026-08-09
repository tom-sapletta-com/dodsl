"""doDSL public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dodsl")
except PackageNotFoundError:  # source checkout without installation
    __version__ = "0+unknown"
