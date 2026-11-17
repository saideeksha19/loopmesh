"""Shared API schema primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UnitQuantity(BaseModel):
    unit: str
    quantity: float


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
    has_more: bool


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: str
    uptime_seconds: float
    timestamp: datetime


class LivenessResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID | None = None
    actor: str
    severity: str
    summary: str
    detail: str | None = None
    created_at: datetime
    is_demo: bool = False


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)
