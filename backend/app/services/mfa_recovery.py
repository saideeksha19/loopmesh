"""Break-glass MFA recovery for infrastructure operators.

There is deliberately no HTTP route for this procedure.  It requires database
credentials plus server-shell access, a recorded approval reference and an
evidence-file hash supplied by the infrastructure operator.  It clears only the
target operator's factor and revokes that operator's sessions; the platform flag
is not changed.  Ordinary platform operators therefore cannot call it.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.sessions import revoke_all_for_user
from app.db.enums import AuditSeverity
from app.db.models.identity import User
from app.services import audit
from app.services import mfa as mfa_service


def break_glass_reset(
    db: Session,
    *,
    email: str,
    performed_by: str,
    approval_reference: str,
    evidence_sha256: str,
    reason: str,
    commit: bool = True,
) -> dict[str, str | int]:
    target_email = (email or "").strip().lower()
    operator = (performed_by or "").strip()
    approval = (approval_reference or "").strip()
    evidence = (evidence_sha256 or "").strip().lower()
    justification = (reason or "").strip()
    if not target_email or not operator or not approval or not justification:
        raise ValidationError(
            "Break-glass recovery requires target, operator, approval reference and reason.",
            details={"reason": "break_glass_evidence_required"},
        )
    if not re.fullmatch(r"[0-9a-f]{64}", evidence):
        raise ValidationError(
            "Break-glass recovery requires the SHA-256 of the approval evidence file.",
            details={"reason": "break_glass_evidence_hash_required"},
        )

    user = db.scalar(select(User).where(User.email == target_email))
    if user is None:
        raise NotFoundError("No operator account matches that email.")
    if not user.is_platform_admin:
        raise ValidationError(
            "Break-glass recovery is limited to platform operator accounts.",
            details={"reason": "platform_operator_required"},
        )
    if user.mfa_enrolled_at is None and not user.mfa_secret_encrypted:
        raise ValidationError(
            "That operator is not enrolled in MFA; no break-glass reset is needed.",
            details={"reason": "not_enrolled"},
        )

    revoked = revoke_all_for_user(db, user.id, reason="mfa_break_glass")
    mfa_service.clear_enrollment(db, user)
    audit.record_event(
        db,
        event_type="platform.mfa.break_glass",
        entity_type="user",
        entity_id=user.id,
        actor=operator,
        actor_id=operator,
        severity=AuditSeverity.CRITICAL,
        summary="Platform MFA factor cleared through documented break-glass procedure.",
        payload={
            "target_user_id": str(user.id),
            "target_email": target_email,
            "approval_reference": approval,
            "evidence_sha256": evidence,
            "reason": justification,
            "revoked_sessions": revoked,
            "platform_flag_unchanged": True,
        },
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        "target_user_id": str(user.id),
        "revoked_sessions": revoked,
        "approval_reference": approval,
        "evidence_sha256": evidence,
    }
