"""Database package."""
from app.db.audit import write_audit_trace, get_audit_trace
__all__ = ["write_audit_trace", "get_audit_trace"]
