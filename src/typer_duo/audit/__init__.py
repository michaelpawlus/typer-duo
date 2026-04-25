"""Static-analysis audit for Typer CLIs.

Use :func:`audit_project` to inspect a target repository's Typer commands and
emit structured findings about agent-readiness (``--json`` flag, dual-output
patterns, etc.) without ever executing the target.
"""

from .ast_walker import audit_project
from .models import AuditReport, EntryPoint, Finding

__all__ = ["audit_project", "AuditReport", "EntryPoint", "Finding"]
