"""Version 1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agents,
    auth,
    audit,
    demands,
    health,
    ledger,
    materials,
    members,
    network,
    opportunities,
    optimization,
    organizations,
    overview,
    platform,
    proposals,
    transactions,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(overview.router)
# Registered before /organizations so the literal /organizations/members path is
# never captured by the /organizations/{organization_id} route.
api_router.include_router(members.router)
api_router.include_router(organizations.router)
api_router.include_router(platform.router)
api_router.include_router(materials.router)
api_router.include_router(demands.router)
api_router.include_router(opportunities.router)
api_router.include_router(network.router)
api_router.include_router(ledger.router)
api_router.include_router(agents.router)
api_router.include_router(optimization.router)
api_router.include_router(proposals.router)
api_router.include_router(transactions.router)
api_router.include_router(audit.router)
