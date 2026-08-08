class DoDslError(RuntimeError):
    """Base error exposed by the doDSL API."""


class DoDslValidationError(DoDslError):
    """Input or generated contract failed deterministic validation."""


class DoDslConflict(DoDslError):
    """The requested operation conflicts with current workspace state."""


class DoDslDependencyError(DoDslError):
    """A required system-owned adapter is unavailable or failed."""
