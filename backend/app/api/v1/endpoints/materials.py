"""Material stream registration and retrieval endpoints."""

from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.api.deps import ActorDep, DbSession, PageParams, build_page
from app.core.authorization import (
    ensure_read_organization,
    require_owned_organization,
    resolve_requested_organization,
)
from app.core.exceptions import ConflictError, ForbiddenError, ImportRejectedError, NotFoundError
from app.core.permissions import Permission
from app.db.enums import DataSource, MaterialCategory, MaterialCondition, MaterialStatus, MaterialUnit
from app.db.models.material import Material, MaterialSpecification
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.organization import Organization
from app.schemas.common import Page
from app.schemas.material import (
    CsvImportError,
    CsvImportReport,
    MaterialCreate,
    MaterialRead,
    MaterialSummary,
)
from app.services import audit

router = APIRouter(prefix="/materials", tags=["materials"])

CSV_REQUIRED_HEADERS = {
    "organization_slug",
    "reference_code",
    "name",
    "category",
    "unit",
    "quantity_available",
}


def _load_material_detail(session: DbSession, material: Material) -> MaterialRead:
    """Load a material with specification and related counts."""
    material_id = material.id
    fresh = session.scalar(
        select(Material)
        .where(Material.id == material_id)
        .options(joinedload(Material.organization), joinedload(Material.specification))
    )
    if fresh is None:  # pragma: no cover - material was loaded moments earlier
        raise NotFoundError("Material stream not found.")
    opportunity_count = int(
        session.scalar(
            select(func.count(RecoveryOpportunity.id)).where(
                RecoveryOpportunity.material_id == material_id
            )
        )
        or 0
    )
    data = MaterialRead.model_validate(fresh, from_attributes=True)
    return data.model_copy(update={"opportunity_count": opportunity_count})


def create_material_record(
    session: DbSession, payload: MaterialCreate, actor: ActorDep | None = None
) -> Material:
    """Persist a validated material profile plus its optional specification."""
    organization_id = payload.organization_id
    if actor is not None:
        if actor.platform_scope:
            organization_id = payload.organization_id
        elif actor.organization_id is not None:
            # Never trust a client-supplied organization as proof of authority.
            organization_id = actor.organization_id
        else:
            raise ForbiddenError(
                "Select an active organisation before creating a material stream.",
                details={"reason": "organization_context_required"},
            )
        require_owned_organization(actor, organization_id, operation="create_material")
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise NotFoundError(
            "Organization not found.", details={"organization_id": str(organization_id)}
        )

    if payload.availability_end is not None and payload.availability_end < payload.availability_start:
        raise ValueError("availability_end must be on or after availability_start")

    fields = payload.model_dump(exclude={"specification"})
    fields["organization_id"] = organization_id
    material = Material(**fields, data_source=DataSource.FORM, is_demo=False)
    session.add(material)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "A material stream with this reference code already exists.",
            details={"reference_code": payload.reference_code},
        ) from exc

    if payload.specification is not None:
        spec = MaterialSpecification(material_id=material.id, **payload.specification.model_dump())
        session.add(spec)
        session.flush()

    audit.record_event(
        session,
        event_type="material.created",
        entity_type="material",
        entity_id=material.id,
        actor=actor.actor_id if actor is not None else "api",
        actor_id=actor.actor_id if actor is not None else None,
        organization_id=material.organization_id,
        summary=f"Registered material stream '{material.name}' ({material.reference_code}).",
        payload={
            "organization_id": str(material.organization_id),
            "category": material.category.value,
            "quantity_available": material.quantity_available,
            "unit": material.unit.value,
        },
    )
    session.commit()
    session.refresh(material)
    return material


@router.get("", response_model=Page[MaterialSummary], summary="List material streams")
def list_materials(
    session: DbSession,
    actor: ActorDep,
    pagination: PageParams,
    material_status: MaterialStatus | None = Query(None, alias="status"),
    category: MaterialCategory | None = None,
    unit: MaterialUnit | None = None,
    condition: MaterialCondition | None = None,
    hazard_class: str | None = Query(None, max_length=120),
    organization_id: UUID | None = None,
) -> Page[MaterialSummary]:
    actor.require(Permission.MATERIAL_VIEW)
    requested_org = resolve_requested_organization(
        actor, organization_id, operation="list_materials"
    )
    stmt = select(Material).options(joinedload(Material.organization))
    if material_status is not None:
        stmt = stmt.where(Material.status == material_status)
    if category is not None:
        stmt = stmt.where(Material.category == category)
    if unit is not None:
        stmt = stmt.where(Material.unit == unit)
    if condition is not None:
        stmt = stmt.where(Material.condition == condition)
    if hazard_class is not None:
        stmt = stmt.where(Material.hazard_class.ilike(f"%{hazard_class}%"))
    if requested_org is not None:
        stmt = stmt.where(Material.organization_id == requested_org)
    elif not actor.sees_all_records:
        if not actor.organization_ids:
            stmt = stmt.where(Material.organization_id.is_(None))
        else:
            stmt = stmt.where(Material.organization_id.in_(actor.organization_ids))

    items = list(
        session.scalars(
            stmt.order_by(Material.created_at.desc(), Material.id)
            .offset(pagination.offset)
            .limit(pagination.page_size)
        ).all()
    )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return build_page(
        MaterialSummary,
        [MaterialSummary.model_validate(item, from_attributes=True) for item in items],
        int(total),
        pagination,
    )


@router.get("/{material_id}", response_model=MaterialRead, summary="Material profile detail")
def get_material(material_id: UUID, session: DbSession, actor: ActorDep) -> MaterialRead:
    actor.require(Permission.MATERIAL_VIEW)
    material = session.scalar(
        select(Material)
        .where(Material.id == material_id)
        .options(joinedload(Material.organization))
    )
    if material is None:
        raise NotFoundError("Material stream not found.", details={"material_id": str(material_id)})
    ensure_read_organization(
        actor, material.organization_id, not_found="Material stream not found."
    )
    return _load_material_detail(session, material)


@router.post(
    "",
    response_model=MaterialRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a material stream",
)
def register_material(payload: MaterialCreate, session: DbSession, actor: ActorDep) -> MaterialRead:
    actor.require(Permission.MATERIAL_CREATE)
    material = create_material_record(session, payload, actor=actor)
    return _load_material_detail(session, material)


def _parse_csv_number(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    return float(stripped) if stripped else None


def _parse_csv_row(
    row_number: int, row: dict[str, str | None], organizations: dict[str, Organization]
) -> MaterialCreate:
    slug = (row.get("organization_slug") or "").strip()
    organization = organizations.get(slug)
    if organization is None:
        raise ValueError(f"unknown or unauthorized organization_slug '{slug}'")

    specification = None
    purity = _parse_csv_number(row.get("purity_pct"))
    moisture = _parse_csv_number(row.get("moisture_pct"))
    contamination = _parse_csv_number(row.get("contamination_pct"))
    if any(value is not None for value in (purity, moisture, contamination)):
        specification = {
            "purity_pct": purity,
            "moisture_pct": moisture,
            "contamination_pct": contamination,
        }

    return MaterialCreate.model_validate(
        {
            "organization_id": organization.id,
            "reference_code": (row.get("reference_code") or "").strip(),
            "name": (row.get("name") or "").strip(),
            "description": (row.get("description") or "").strip() or None,
            "category": (row.get("category") or "").strip().lower(),
            "quantity_available": (row.get("quantity_available") or "").strip(),
            "unit": (row.get("unit") or "").strip().lower(),
            "condition": (row.get("condition") or "as_generated").strip().lower(),
            "hazard_class": (row.get("hazard_class") or "").strip() or None,
            "handling_requirements": (row.get("handling_requirements") or "").strip() or None,
            "packaging": (row.get("packaging") or "").strip() or None,
            "availability_start": (row.get("availability_start") or "").strip(),
            "availability_end": (row.get("availability_end") or "").strip() or None,
            "status": "available",
            "specification": specification,
        }
    )


@router.post(
    "/import",
    response_model=CsvImportReport,
    status_code=status.HTTP_201_CREATED,
    summary="Import material streams from a CSV upload",
)
async def import_materials(
    session: DbSession,
    actor: ActorDep,
    file: UploadFile = File(..., description="CSV file of material streams"),
) -> CsvImportReport:
    actor.require(Permission.MATERIAL_IMPORT)
    if not actor.platform_scope and actor.organization_id is None:
        raise ForbiddenError(
            "Select an active organisation before importing materials.",
            details={"reason": "organization_context_required"},
        )
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise ImportRejectedError(
            "Only CSV uploads are accepted for material import.",
            details={"filename": filename},
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise ImportRejectedError("The uploaded CSV file is empty.", details={"filename": filename})

    try:
        decoded = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportRejectedError(
            "Material imports must be UTF-8 encoded CSV files.",
            details={"filename": filename},
        ) from exc

    reader = csv.DictReader(io.StringIO(decoded))
    headers = {header.strip() for header in (reader.fieldnames or []) if header}
    missing = sorted(CSV_REQUIRED_HEADERS - headers)
    if missing:
        raise ImportRejectedError(
            "The uploaded CSV is missing required columns.",
            details={"filename": filename, "missing_columns": missing},
        )

    rows = list(reader)
    if not rows:
        raise ImportRejectedError(
            "The uploaded CSV has a header row but no data rows.",
            details={"filename": filename},
        )

    org_query = select(Organization)
    if not actor.platform_scope:
        org_query = org_query.where(Organization.id.in_(actor.organization_ids))
    organizations = {
        organization.slug: organization for organization in session.scalars(org_query).all()
    }
    existing_codes = {code for code in session.scalars(select(Material.reference_code)).all()}

    created = 0
    created_codes: list[str] = []
    errors: list[CsvImportError] = []

    for index, raw_row in enumerate(rows, start=2):
        row = {key: (value or "") for key, value in (raw_row or {}).items() if key}
        if not any(value.strip() for value in row.values()):
            continue
        try:
            with session.begin_nested():
                payload = _parse_csv_row(index, row, organizations)
                if not actor.platform_scope and payload.organization_id != actor.organization_id:
                    raise ValueError("organization_slug is not your active organisation")
                if payload.reference_code in existing_codes:
                    raise ValueError(f"reference_code '{payload.reference_code}' already exists")
                material = Material(
                    **payload.model_dump(exclude={"specification"}),
                    data_source=DataSource.CSV,
                    is_demo=False,
                )
                session.add(material)
                session.flush()
                if payload.specification is not None:
                    session.add(
                        MaterialSpecification(
                            material_id=material.id,
                            **payload.specification.model_dump(),
                        )
                    )
            existing_codes.add(payload.reference_code)
            created_codes.append(payload.reference_code)
            created += 1
        except Exception as exc:  # noqa: BLE001 - row-level reporting is intentional
            ref = (row.get("reference_code") or "").strip()
            prefix = f"[{ref}] " if ref else ""
            errors.append(CsvImportError(row=index, message=f"{prefix}{exc}"))

    if created:
        audit.record_event(
            session,
            event_type="materials.imported",
            entity_type="material",
            actor=actor.actor_id,
            actor_id=actor.actor_id,
            organization_id=actor.organization_id,
            summary=f"CSV import '{filename}' created {created} material stream(s).",
            severity="warning" if errors else "info",
            payload={
                "filename": filename,
                "rows_received": len(rows),
                "created": created,
                "skipped": len(errors),
                "errors": [error.model_dump() for error in errors],
            },
        )
        session.commit()

    return CsvImportReport(
        filename=filename,
        rows_received=len(rows),
        created=created,
        skipped=len(errors),
        errors=errors,
        created_reference_codes=created_codes,
        status="completed",
    )
