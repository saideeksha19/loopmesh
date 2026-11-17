"""Circular Impact Ledger endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActorDep, DbSession
from app.core.permissions import Permission
from app.schemas.ledger import LedgerReport
from app.services.ledger import build_ledger

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("", response_model=LedgerReport, summary="Recovery ledger by verification state")
def get_ledger(session: DbSession, actor: ActorDep) -> LedgerReport:
    actor.require(Permission.TRANSACTION_VIEW)
    return LedgerReport.model_validate(build_ledger(session, actor=actor))
