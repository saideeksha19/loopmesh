"""Organization schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict

from app.schemas.common import ApiModel


class OrganizationSummary(ApiModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    sector: str
    city: str | None = None
    country: str
    is_demo: bool = False


class OrganizationRead(OrganizationSummary):
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    description: str | None = None
    data_source: str
    material_streams: int = 0
    open_demands: int = 0
    created_at: datetime
    updated_at: datetime
