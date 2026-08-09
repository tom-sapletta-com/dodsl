"""Pure doDSL schemas, models, validators and DSL renderers."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dodsl-contracts")
except PackageNotFoundError:
    __version__ = "0+unknown"
