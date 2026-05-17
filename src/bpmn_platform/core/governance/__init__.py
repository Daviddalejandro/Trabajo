"""Reglas de gobierno empresarial (validaciones semanticas base)."""
from .rules import GovernanceIssue, IssueSeverity, validate_activity_name

__all__ = ["GovernanceIssue", "IssueSeverity", "validate_activity_name"]
