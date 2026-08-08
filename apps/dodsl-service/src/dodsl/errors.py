"""Compatibility exports; import from dodsl_contracts.errors in new code."""

from dodsl_contracts.errors import DoDslConflict, DoDslDependencyError, DoDslError, DoDslValidationError

__all__ = ["DoDslConflict", "DoDslDependencyError", "DoDslError", "DoDslValidationError"]
