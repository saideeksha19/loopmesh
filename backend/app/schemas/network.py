"""Resource network graph schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import UnitQuantity


class NetworkNode(BaseModel):
    id: UUID
    name: str
    slug: str
    sector: str
    city: str | None = None
    country: str
    is_demo: bool
    material_streams: int
    open_demands: int
    outbound_links: int
    inbound_links: int


class NetworkEdge(BaseModel):
    id: str
    source: UUID
    target: UUID
    category: str
    status: str  # "potential" | "confirmed"
    opportunity_count: int
    confirmed_transactions: int
    quantity_by_unit: list[UnitQuantity]


class NetworkSummary(BaseModel):
    organizations: int
    potential_links: int
    confirmed_links: int
    total_material_streams: int
    unlinked_organizations: int


class NetworkGraph(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    summary: NetworkSummary
    legend: dict[str, str]
