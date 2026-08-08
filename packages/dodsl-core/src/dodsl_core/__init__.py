"""doDSL workspace runtime and dependency ports."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dodsl-core")
except PackageNotFoundError:
    __version__ = "0.1.0"

from .workspace import ProjectWorkspace

__all__ = ["ProjectWorkspace", "__version__"]
