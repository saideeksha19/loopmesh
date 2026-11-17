"""Material schemas — the structured 'Material DNA' contract."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.enums import (
    DataSource,
    MaterialCategory,
    MaterialCondition,
    MaterialStatus,
    MaterialUnit,
)
from app.schemas.organization import OrganizationSummary

REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,47}$"


class CompositionEntry(BaseModel):
    substance: str = Field(min_length=1, max_length=80)
    pct: float = Field(ge=0, le=100)


class MaterialSpecificationBase(BaseModel):
    purity_pct: float | None = Field(default=None, ge=0, le=100)
    moisture_pct: float | None = Field(default=None, ge=0, le=100)
    contamination_pct: float | None = Field(default=None, ge=0, le=100)
    ph_value: float | None = Field(default=None, ge=0, le=14)
    particle_size_mm: float | None = Field(default=None, gt=0, le=100_000)
    calorific_value_mj_kg: float | None = Field(default=None, ge=0, le=1000)
    composition: list[CompositionEntry] = Field(default_factory=list, max_length=40)
    contaminants: dict[str, float] = Field(default_factory=dict)
    assay_method: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("contaminants")
    @classmethod
    def _validate_contaminants(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 40:
            raise ValueError("at most 40 contaminant entries are allowed")
        for key, pct in value.items():
            if not key or len(key) > 80:
                raise ValueError("contaminant names must be 1-80 characters")
            if pct < 0 or pct > 100:
                raise ValueError(f"contaminant '{key}' must be between 0 and 100 percent")
        return value


class MaterialSpecificationCreate(MaterialSpecificationBase):
    pass


class MaterialSpecificationRead(MaterialSpecificationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class MaterialCreate(BaseModel):
    organization_id: UUID
    reference_code: str = Field(min_length=2, max_length=48, pattern=REFERENCE_PATTERN)
    name: str = Field(min_length=2, max_length=160)
    category: MaterialCategory
    description: str | None = Field(default=None, max_length=2000)
    quantity_available: float = Field(gt=0, le=1_000_000_000)
    unit: MaterialUnit = MaterialUnit.TONNE
    condition: MaterialCondition = MaterialCondition.AS_GENERATED
    status: MaterialStatus = MaterialStatus.AVAILABLE
    hazard_class: str | None = Field(default=None, max_length=40)
    handling_requirements: str | None = Field(default=None, max_length=2000)
    origin_process: str | None = Field(default=None, max_length=160)
    availability_start: date | None = None
    availability_end: date | None = None
    specification: MaterialSpecificationCreate | None = None

    @field_validator("reference_code", "name", mode="before")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "description", "hazard_class", "handling_requirements", "origin_process", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @model_validator(mode="after")
    def _check_window(self) -> "MaterialCreate":
        if (
            self.availability_start
            and self.availability_end
            and self.availability_end < self.availability_start
        ):
            raise ValueError("availability_end must be on or after availability_start")
        return self


class MaterialSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference_code: str
    name: str
    category: MaterialCategory
    quantity_available: float
    unit: MaterialUnit
    condition: MaterialCondition
    status: MaterialStatus
    hazard_class: str | None = None
    organization: OrganizationSummary
    availability_start: date | None = None
    availability_end: date | None = None
    data_source: DataSource
    is_demo: bool
    created_at: datetime


class MaterialRead(MaterialSummary):
    description: str | None = None
    handling_requirements: str | None = None
    origin_process: str | None = None
    specification: MaterialSpecificationRead | None = None
    opportunity_count: int = 0


class CsvImportError(BaseModel):
    row: int
    message: str


class CsvImportReport(BaseModel):
    filename: str
    rows_received: int
    created: int
    skipped: int
    errors: list[CsvImportError]
    created_reference_codes: list[str]
    status: Literal["completed", "rejected"] = "completed"
    demo_hint: str = (
        "Imported rows are stored as user-supplied data (data_source=csv). "
        "The sample CSV is demo content only."
    )
