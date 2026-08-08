"""System-owned source, knowledge and SSOT adapters for doDSL."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dodsl-adapters")
except PackageNotFoundError:
    __version__ = "0.1.0"

from .knowledge import KnowledgeCompiler
from .sources import GitSnapshotter, UploadImporter, WebSnapshotter
from .ssot import SsotBridge

__all__ = [
    "GitSnapshotter", "KnowledgeCompiler", "SsotBridge", "UploadImporter", "WebSnapshotter",
    "__version__",
]
