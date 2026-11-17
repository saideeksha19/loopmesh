"""LOOPMESH API application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import engine
from app.schemas.common import LivenessResponse

configure_logging(settings)
logger = logging.getLogger("loopmesh.app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_runtime_security()
    logger.info(
        "starting api",
        extra={
            "environment": settings.environment,
            "database_dialect": engine.dialect.name,
            "ai_enabled": settings.ai_enabled,
            "version": settings.app_version,
        },
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - readiness is reported by /api/v1/health
        logger.exception("database not reachable at startup")
    yield
    logger.info("shutting down api")
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={"name": "LOOPMESH", "url": "https://github.com/loopmesh"},
    openapi_tags=[
        {"name": "system", "description": "Liveness and readiness probes."},
        {"name": "overview", "description": "Aggregated dashboard metrics and activity."},
        {"name": "organizations", "description": "Industrial actors in the network."},
        {"name": "materials", "description": "Material DNA profiles and CSV ingestion."},
        {"name": "demands", "description": "Resource demand specifications."},
        {"name": "opportunities", "description": "Deterministic matches and rule evidence."},
        {"name": "network", "description": "Resource knowledge graph."},
        {"name": "ledger", "description": "Recovery states and verified quantities."},
        {"name": "agents", "description": "Planned agent registry (no runtime in Phase 1)."},
        {"name": "optimization", "description": "Planned optimization engine contract."},
        {"name": "proposals", "description": "Recovery proposal lifecycle and transitions."},
        {"name": "transactions", "description": "Transfer execution and verification."},
        {"name": "audit", "description": "Immutable audit journal (read-only)."},
    ],
)

# Order matters: the last added middleware runs first. Request context wraps
# CORS so allowed requests keep correlation IDs; TrustedHost is outermost so an
# unauthorized Host header is rejected before routing or other middleware.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*", settings.auth_csrf_header],
    expose_headers=[settings.request_id_header, "X-Response-Time-ms"],
    max_age=600,
)
app.add_middleware(
    RequestContextMiddleware,
    header_name=settings.request_id_header,
    skip_paths=("/health",),
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_host_list,
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_v1_prefix,
    }


@app.get(
    "/health",
    response_model=LivenessResponse,
    tags=["system"],
    summary="Liveness probe",
    description="Process-level liveness check that does not touch the database.",
)
def liveness() -> LivenessResponse:
    return LivenessResponse(service=settings.app_name, version=settings.app_version)
