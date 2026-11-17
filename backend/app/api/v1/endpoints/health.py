"""Health and readiness endpoints."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.common import HealthResponse

logger = logging.getLogger("loopmesh.health")

router = APIRouter(tags=["system"])

APP_STARTED_AT = time.monotonic()


@router.get("/health", response_model=HealthResponse, summary="Readiness probe")
def readiness(response: Response, session: Session = Depends(get_db)) -> HealthResponse:
    """Report API and database status. Returns 503 when the database is down."""
    database_state = "reachable"
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("readiness probe could not reach the database")
        database_state = "unreachable"
        response.status_code = 503

    return HealthResponse(
        status="ok" if database_state == "reachable" else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database=database_state,
        uptime_seconds=round(time.monotonic() - APP_STARTED_AT, 2),
        timestamp=datetime.now(timezone.utc),
    )
