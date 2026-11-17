"""Audit journal API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AuditRecordRead(BaseModel):
    id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID | None = None
    previous_state: str | None = None
    new_state: str | None = None
    actor: str
    actor_id: str | None = None
    organization_id: UUID | None = None
    severity: str
    summary: str
    reason: str | None = None
    detail: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
