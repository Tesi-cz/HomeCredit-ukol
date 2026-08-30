"""ORM modely registru (database.md).

Import tohoto balíčku zaregistruje všechny tabulky do `Base.metadata`. Na tom
stojí `create_all` v testech i autogenerace úvodní Alembic revize (úkol 4.5) —
Alembic vidí jen ty tabulky, jejichž modely byly naimportovány.
"""

from __future__ import annotations

from regina.db.base import Base
from regina.db.models.applications import Application
from regina.db.models.audit_log import AuditLog
from regina.db.models.classification_log import ClassificationLog
from regina.db.models.classification_suggestion import ClassificationSuggestion
from regina.db.models.llm_call_log import LLMCallLog
from regina.db.models.users import User

__all__ = [
    "Base",
    "User",
    "Application",
    "ClassificationLog",
    "ClassificationSuggestion",
    "LLMCallLog",
    "AuditLog",
]
