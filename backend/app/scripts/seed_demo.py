"""Load the LOOPMESH demo dataset.

Everything written by this script is explicitly demo data: every row carries
``is_demo=True`` and ``data_source=demo``, organisations use reserved
``.example`` e-mail domains, and the UI displays a demo banner.

Usage (from ``backend/``)::

    python -m app.scripts.seed_demo            # load if the database is empty
    python -m app.scripts.seed_demo --reset    # wipe LOOPMESH tables first

The script refuses to run when ENVIRONMENT=production.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.enums import (
    AgentName,
    AgentRunStatus,
    DataSource,
    DemandFrequency,
    DemandStatus,
    MaterialCategory,
    MaterialCondition,
    MaterialStatus,
    MaterialUnit,
    OpportunityStatus,
    OrganizationSector,
    ProposalStatus,
    TransactionStatus,
    VerificationMethod,
)
from app.db.models.agent import AgentExecution
from app.db.models.audit import AuditEvent, AuditIntegrityState
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material, MaterialSpecification
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.organization import Organization
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.db.session import SessionLocal
from app.services import audit
from app.services.discovery import discover_opportunities

TODAY = date.today()
NOW = datetime.now(timezone.utc)


def _days(count: int) -> datetime:
    return NOW - timedelta(days=count)


DEMO_ORGANIZATIONS: list[dict] = [
    {
        "slug": "aurelia-chemicals",
        "name": "Aurelia Chemicals",
        "sector": OrganizationSector.CHEMICALS,
        "country": "Netherlands",
        "region": "Zuid-Holland",
        "city": "Rotterdam",
        "latitude": 51.9244,
        "longitude": 4.4777,
        "contact_name": "Process Recovery Desk",
        "contact_email": "recovery@aurelia.example",
        "description": "Specialty chemicals site with solvent, acid and gypsum byproducts.",
    },
    {
        "slug": "meridian-steel",
        "name": "Meridian Steel Works",
        "sector": OrganizationSector.STEEL_METALS,
        "country": "Belgium",
        "region": "Flanders",
        "city": "Ghent",
        "latitude": 51.0543,
        "longitude": 3.7174,
        "contact_name": "Byproduct Valorisation",
        "contact_email": "byproducts@meridian.example",
        "description": "Integrated steel plant producing slag, mill scale and scrap.",
    },
    {
        "slug": "solvane-polymers",
        "name": "Solvane Polymers",
        "sector": OrganizationSector.PLASTICS_POLYMERS,
        "country": "Belgium",
        "region": "Flanders",
        "city": "Antwerp",
        "latitude": 51.2194,
        "longitude": 4.4025,
        "contact_name": "Secondary Materials",
        "contact_email": "secondary@solvane.example",
        "description": "Polymer compounding plant with regrind and film offcuts.",
    },
    {
        "slug": "terranova-foods",
        "name": "TerraNova Foods",
        "sector": OrganizationSector.FOOD_AGRICULTURE,
        "country": "France",
        "region": "Hauts-de-France",
        "city": "Lille",
        "latitude": 50.6292,
        "longitude": 3.0573,
        "contact_name": "Residue Streams Team",
        "contact_email": "residues@terranova.example",
        "description": "Food processing group with organic residues and recovered oils.",
    },
    {
        "slug": "helios-cement",
        "name": "Helios Cement",
        "sector": OrganizationSector.CEMENT_MINERALS,
        "country": "Netherlands",
        "region": "Limburg",
        "city": "Maastricht",
        "latitude": 50.8514,
        "longitude": 5.6910,
        "contact_name": "Alternative Raw Materials",
        "contact_email": "arm@helios.example",
        "description": "Cement producer seeking mineral and iron-rich secondary feedstock.",
    },
    {
        "slug": "verdant-textiles",
        "name": "Verdant Textiles",
        "sector": OrganizationSector.TEXTILES,
        "country": "Belgium",
        "region": "Flanders",
        "city": "Kortrijk",
        "latitude": 50.8260,
        "longitude": 3.2649,
        "contact_name": "Fibre Recovery",
        "contact_email": "fibre@verdant.example",
        "description": "Textile mill generating cotton and wool offcuts.",
    },
    {
        "slug": "circulus-glass",
        "name": "Circulus Glass",
        "sector": OrganizationSector.GLASS_CERAMICS,
        "country": "Belgium",
        "region": "Wallonia",
        "city": "Charleroi",
        "latitude": 50.4108,
        "longitude": 4.4446,
        "contact_name": "Cullet Office",
        "contact_email": "cullet@circulus.example",
        "description": "Container glass plant with colour-sorted cullet streams.",
    },
    {
        "slug": "northgate-packaging",
        "name": "Northgate Packaging",
        "sector": OrganizationSector.PAPER_PACKAGING,
        "country": "Netherlands",
        "region": "Noord-Brabant",
        "city": "Tilburg",
        "latitude": 51.5606,
        "longitude": 5.0913,
        "contact_name": "Materials Sourcing",
        "contact_email": "sourcing@northgate.example",
        "description": "Packaging converter buying recycled polymer and fibre feedstock.",
    },
    {
        "slug": "aqualoop-utilities",
        "name": "AquaLoop Utilities",
        "sector": OrganizationSector.WATER_TREATMENT,
        "country": "Netherlands",
        "region": "Drenthe",
        "city": "Emmen",
        "latitude": 52.7792,
        "longitude": 6.9064,
        "contact_name": "Industrial Water Desk",
        "contact_email": "industrial@aqualoop.example",
        "description": "Industrial water utility producing reclaimed process water.",
    },
    {
        "slug": "brightfield-energy",
        "name": "Brightfield Energy",
        "sector": OrganizationSector.ENERGY_UTILITIES,
        "country": "Netherlands",
        "region": "Limburg",
        "city": "Geleen",
        "latitude": 50.9697,
        "longitude": 5.8285,
        "contact_name": "Fuel Sourcing",
        "contact_email": "fuels@brightfield.example",
        "description": "Energy plant co-firing waste-derived fuels and biomass residues.",
    },
    {
        "slug": "limburg-aggregates",
        "name": "Limburg Aggregates",
        "sector": OrganizationSector.CONSTRUCTION,
        "country": "Netherlands",
        "region": "Limburg",
        "city": "Heerlen",
        "latitude": 50.8882,
        "longitude": 5.9795,
        "contact_name": "Aggregate Substitution",
        "contact_email": "aggregates@limburg.example",
        "description": "Aggregates producer substituting secondary mineral streams.",
    },
    {
        "slug": "portside-logistics",
        "name": "Portside Logistics",
        "sector": OrganizationSector.LOGISTICS,
        "country": "Netherlands",
        "region": "Zeeland",
        "city": "Vlissingen",
        "latitude": 51.4421,
        "longitude": 3.5736,
        "contact_name": "Warehouse Operations",
        "contact_email": "warehouse@portside.example",
        "description": "Port warehousing group with packaging and dunnage streams.",
    },
]


DEMO_MATERIALS: list[dict] = [
    {
        "org": "aurelia-chemicals",
        "ref": "LM-0001",
        "name": "Spent sulphuric acid (78%)",
        "category": MaterialCategory.CHEMICALS,
        "quantity": 420,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "corrosive",
        "origin": "Alkylation and pickling lines",
        "handling": "Acid-resistant tanker, bunded transfer, PPE level 2.",
        "description": "Filtered spent acid with residual hydrocarbon content.",
        "spec": {
            "purity_pct": 78,
            "contamination_pct": 4.5,
            "moisture_pct": 12,
            "ph_value": 1.2,
            "assay_method": "Internal titration (Q3 2026)",
        },
    },
    {
        "org": "aurelia-chemicals",
        "ref": "LM-0002",
        "name": "Gypsum filter cake",
        "category": MaterialCategory.MINERALS,
        "quantity": 1250,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Flue-gas desulphurisation",
        "handling": "Covered tipper, keep dry.",
        "description": "FGD gypsum filter cake, free of visible contamination.",
        "spec": {
            "purity_pct": 92,
            "contamination_pct": 1.8,
            "moisture_pct": 18,
            "ph_value": 6.8,
            "composition": [
                {"substance": "CaSO4·2H2O", "pct": 92.0},
                {"substance": "Inert fines", "pct": 6.2},
            ],
            "assay_method": "External laboratory certificate",
        },
    },
    {
        "org": "aurelia-chemicals",
        "ref": "LM-0003",
        "name": "Off-spec ethanol",
        "category": MaterialCategory.CHEMICALS,
        "quantity": 180,
        "unit": MaterialUnit.CUBIC_METRE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "flammable",
        "origin": "Solvent recovery unit",
        "handling": "ATEX-rated tanker, earthing required.",
        "description": "Off-specification ethanol stream, water content within limits.",
        "spec": {
            "purity_pct": 88,
            "contamination_pct": 2.2,
            "moisture_pct": 6,
            "ph_value": 6.5,
            "assay_method": "GC analysis (Q3 2026)",
        },
    },
    {
        "org": "meridian-steel",
        "ref": "LM-0004",
        "name": "Blast furnace slag",
        "category": MaterialCategory.MINERALS,
        "quantity": 9800,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Blast furnace granulation",
        "handling": "Bulk tipper, moisture-sensitive for milling.",
        "description": "Granulated slag, air-cooled fraction available on request.",
        "spec": {
            "purity_pct": 96,
            "contamination_pct": 0.6,
            "moisture_pct": 8,
            "composition": [
                {"substance": "SiO2", "pct": 36.0},
                {"substance": "CaO", "pct": 40.0},
                {"substance": "Al2O3", "pct": 12.0},
            ],
            "assay_method": "Plant laboratory, monthly composite",
        },
    },
    {
        "org": "meridian-steel",
        "ref": "LM-0005",
        "name": "Mill scale",
        "category": MaterialCategory.METALS,
        "quantity": 1400,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "non_hazardous",
        "origin": "Hot rolling mill",
        "handling": "Covered containers, oil residue drainage.",
        "description": "Iron oxide mill scale with residual rolling oil.",
        "spec": {
            "purity_pct": 91,
            "contamination_pct": 2.4,
            "moisture_pct": 2,
            "composition": [{"substance": "Fe3O4", "pct": 91.0}],
            "assay_method": "XRF, plant laboratory",
        },
    },
    {
        "org": "meridian-steel",
        "ref": "LM-0006",
        "name": "Steel scrap offcuts",
        "category": MaterialCategory.METALS,
        "quantity": 2600,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Finishing lines",
        "handling": "Sorted skips, magnet loading.",
        "description": "Sorted low-alloy steel offcuts.",
        "spec": {
            "purity_pct": 97.5,
            "contamination_pct": 0.4,
            "moisture_pct": 0.5,
            "assay_method": "Sorting specification",
        },
    },
    {
        "org": "solvane-polymers",
        "ref": "LM-0007",
        "name": "PET regrind",
        "category": MaterialCategory.POLYMERS,
        "quantity": 480,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Bottle-to-flake line",
        "handling": "Big bags on pallets, dry storage.",
        "description": "Hot-washed PET regrind, food-contact status not declared.",
        "spec": {
            "purity_pct": 94,
            "contamination_pct": 1.2,
            "moisture_pct": 0.6,
            "composition": [{"substance": "PET", "pct": 94.0}],
            "contaminants": {"PVC": 0.3, "Polyolefins": 0.9},
            "assay_method": "NIR sorting report + lab check",
        },
    },
    {
        "org": "solvane-polymers",
        "ref": "LM-0008",
        "name": "Mixed polyolefin flake",
        "category": MaterialCategory.POLYMERS,
        "quantity": 340,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Post-consumer sorting line",
        "handling": "Big bags, covered storage.",
        "description": "Mixed PP/PE flake from post-consumer packaging.",
        "spec": {
            "purity_pct": 82,
            "contamination_pct": 3.6,
            "moisture_pct": 1.4,
            "contaminants": {"PET": 2.1, "Paper fibre": 1.5},
            "assay_method": "Sorting report",
        },
    },
    {
        "org": "solvane-polymers",
        "ref": "LM-0009",
        "name": "Polymer film offcuts",
        "category": MaterialCategory.POLYMERS,
        "quantity": 240,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "non_hazardous",
        "origin": "Conversion lines",
        "handling": "Baled, dry storage.",
        "description": "Post-industrial LDPE film offcuts, printed fraction separated.",
        "spec": {
            "purity_pct": 88,
            "contamination_pct": 2.1,
            "moisture_pct": 0.9,
            "assay_method": "Supplier declaration",
        },
    },
    {
        "org": "terranova-foods",
        "ref": "LM-0010",
        "name": "Spent grain",
        "category": MaterialCategory.ORGANICS,
        "quantity": 1500,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "non_hazardous",
        "origin": "Brewing operations",
        "handling": "Sealed trailers, 48 h turnover, odour control.",
        "description": "Wet brewer's spent grain, high moisture.",
        "spec": {
            "purity_pct": 92,
            "contamination_pct": 1.0,
            "moisture_pct": 68,
            "ph_value": 4.6,
            "composition": [{"substance": "Organic matter", "pct": 92.0}],
            "assay_method": "Supplier declaration",
        },
    },
    {
        "org": "terranova-foods",
        "ref": "LM-0011",
        "name": "Whey permeate",
        "category": MaterialCategory.ORGANICS,
        "quantity": 900,
        "unit": MaterialUnit.CUBIC_METRE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "non_hazardous",
        "origin": "Dairy processing",
        "handling": "Stainless tanker, chilled.",
        "description": "Liquid whey permeate with high water content.",
        "spec": {
            "purity_pct": 88,
            "contamination_pct": 0.7,
            "moisture_pct": 95,
            "ph_value": 5.8,
            "assay_method": "In-house analysis",
        },
    },
    {
        "org": "terranova-foods",
        "ref": "LM-0012",
        "name": "Waste cooking oil",
        "category": MaterialCategory.ORGANICS,
        "quantity": 260,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Frying lines",
        "handling": "Heated tanker, filtered.",
        "description": "Filtered waste cooking oil suitable for technical use.",
        "spec": {
            "purity_pct": 96,
            "contamination_pct": 0.9,
            "moisture_pct": 0.8,
            "calorific_value_mj_kg": 39.2,
            "assay_method": "Supplier laboratory certificate",
        },
    },
    {
        "org": "verdant-textiles",
        "ref": "LM-0013",
        "name": "Cotton offcuts",
        "category": MaterialCategory.TEXTILES,
        "quantity": 210,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "non_hazardous",
        "origin": "Cut-and-sew lines",
        "handling": "Baled, dry storage.",
        "description": "Unmixed cotton offcuts, undyed fraction available.",
        "spec": {
            "purity_pct": 93,
            "contamination_pct": 1.5,
            "moisture_pct": 6,
            "composition": [{"substance": "Cotton", "pct": 93.0}],
            "assay_method": "Fibre composition certificate",
        },
    },
    {
        "org": "verdant-textiles",
        "ref": "LM-0014",
        "name": "Post-industrial wool waste",
        "category": MaterialCategory.TEXTILES,
        "quantity": 95,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.MIXED,
        "hazard": "non_hazardous",
        "origin": "Weaving",
        "handling": "Baled, dry storage.",
        "description": "Mixed wool/synthetic yarn waste.",
        "spec": {
            "purity_pct": 87,
            "contamination_pct": 4.2,
            "moisture_pct": 9,
            "assay_method": "Supplier declaration",
        },
    },
    {
        "org": "circulus-glass",
        "ref": "LM-0015",
        "name": "Mixed colour cullet",
        "category": MaterialCategory.GLASS,
        "quantity": 2200,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Colour sorting plant",
        "handling": "Covered skips, dust suppression.",
        "description": "Mixed colour container cullet with ceramic contamination.",
        "spec": {
            "purity_pct": 90,
            "contamination_pct": 5.5,
            "moisture_pct": 1,
            "contaminants": {"Ceramics": 3.2, "Metals": 0.6},
            "assay_method": "Sorting plant report",
        },
    },
    {
        "org": "aqualoop-utilities",
        "ref": "LM-0016",
        "name": "Reclaimed process water",
        "category": MaterialCategory.WATER,
        "quantity": 4500,
        "unit": MaterialUnit.CUBIC_METRE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Membrane bioreactor",
        "handling": "Pipeline or tanker, chlorine residual monitoring.",
        "description": "Class A reclaimed water for industrial reuse.",
        "spec": {
            "purity_pct": 96,
            "contamination_pct": 0.8,
            "ph_value": 7.2,
            "assay_method": "Continuous online monitoring",
        },
    },
    {
        "org": "brightfield-energy",
        "ref": "LM-0017",
        "name": "Waste-derived biomass residue",
        "category": MaterialCategory.ORGANICS,
        "quantity": 1800,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.PROCESSED,
        "hazard": "non_hazardous",
        "origin": "Fuel preparation",
        "handling": "Covered bunker, fire watch.",
        "description": "Biomass residue from fuel preparation, high moisture.",
        "spec": {
            "purity_pct": 84,
            "contamination_pct": 2.6,
            "moisture_pct": 44,
            "calorific_value_mj_kg": 11.4,
            "assay_method": "Fuel laboratory certificate",
        },
    },
    {
        "org": "brightfield-energy",
        "ref": "LM-0018",
        "name": "Bottom ash",
        "category": MaterialCategory.MINERALS,
        "quantity": 700,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "non_hazardous",
        "origin": "Grate combustion",
        "handling": "Quenched, covered skips.",
        "description": "Bottom ash with residual metals and unburnt carbon.",
        "spec": {
            "purity_pct": 78,
            "contamination_pct": 6.8,
            "moisture_pct": 14,
            "assay_method": "Quarterly laboratory analysis",
        },
    },
    {
        "org": "meridian-steel",
        "ref": "LM-0019",
        "name": "Recovered refractory brick",
        "category": MaterialCategory.MINERALS,
        "quantity": 320,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.UNKNOWN,
        "hazard": None,
        "origin": "Ladle relining",
        "handling": "Not yet assessed — storage under tarpaulin.",
        "description": "Spent refractory brick awaiting characterisation. No assay on file.",
        "spec": None,
    },
    {
        "org": "northgate-packaging",
        "ref": "LM-0020",
        "name": "Waste paper trim",
        "category": MaterialCategory.PAPER,
        "quantity": 540,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "hazard": "non_hazardous",
        "origin": "Corrugator trim",
        "handling": "Baled, dry storage.",
        "description": "Clean corrugator trim, mixed liner grades.",
        "spec": {
            "purity_pct": 89,
            "contamination_pct": 2.8,
            "moisture_pct": 7,
            "assay_method": "Supplier declaration",
        },
    },
    {
        "org": "portside-logistics",
        "ref": "LM-0021",
        "name": "Timber dunnage",
        "category": MaterialCategory.OTHER,
        "quantity": 120,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.MIXED,
        "hazard": "non_hazardous",
        "origin": "Container stripping",
        "handling": "Untreated timber only, stored dry.",
        "description": "Untreated timber dunnage from container handling.",
        "spec": {
            "purity_pct": 80,
            "contamination_pct": 3.0,
            "moisture_pct": 12,
            "assay_method": "Visual sorting protocol",
        },
    },
]


def _demand(
    org: str,
    title: str,
    category: MaterialCategory,
    min_quantity: float,
    max_quantity: float | None,
    unit: MaterialUnit,
    *,
    purity: float | None = None,
    moisture: float | None = None,
    contamination: float | None = None,
    distance: float | None = None,
    hazards: list[str] | None = None,
    price: float | None = None,
    frequency: DemandFrequency = DemandFrequency.CONTINUOUS,
    description: str = "",
) -> dict:
    return {
        "org": org,
        "title": title,
        "category": category,
        "min_quantity": min_quantity,
        "max_quantity": max_quantity,
        "unit": unit,
        "purity": purity,
        "moisture": moisture,
        "contamination": contamination,
        "distance": distance,
        "hazards": hazards or [],
        "price": price,
        "frequency": frequency,
        "description": description,
    }


DEMO_DEMANDS: list[dict] = [
    _demand(
        "helios-cement",
        "Cement kiln slag feedstock",
        MaterialCategory.MINERALS,
        800,
        4000,
        MaterialUnit.TONNE,
        purity=85,
        moisture=12,
        contamination=2.0,
        distance=350,
        hazards=["corrosive", "flammable", "toxic"],
        price=18,
        description="Granulated slag for clinker substitution; dry feed required.",
    ),
    _demand(
        "helios-cement",
        "Gypsum for clinker set control",
        MaterialCategory.MINERALS,
        300,
        1500,
        MaterialUnit.TONNE,
        purity=90,
        moisture=10,
        contamination=1.5,
        distance=400,
        price=22,
        description="Secondary gypsum replacing natural gypsum in clinker grinding.",
    ),
    _demand(
        "helios-cement",
        "Iron-rich mill scale for clinker",
        MaterialCategory.METALS,
        200,
        800,
        MaterialUnit.TONNE,
        purity=88,
        moisture=5,
        contamination=3.0,
        distance=350,
        price=26,
        description="Iron oxide feedstock for clinker mineralisation.",
    ),
    _demand(
        "limburg-aggregates",
        "Glass cullet aggregate substitute",
        MaterialCategory.MINERALS,
        500,
        2500,
        MaterialUnit.TONNE,
        purity=88,
        moisture=3,
        contamination=6.0,
        distance=300,
        price=12,
        description="Cullet as bound aggregate substitute; ceramic contamination tolerated.",
    ),
    _demand(
        "limburg-aggregates",
        "Refractory aggregate for bound applications",
        MaterialCategory.MINERALS,
        100,
        500,
        MaterialUnit.TONNE,
        purity=80,
        moisture=5,
        contamination=3.0,
        distance=250,
        description="Spent refractory crushed as aggregate; characterisation required.",
    ),
    _demand(
        "northgate-packaging",
        "Recycled PET flake",
        MaterialCategory.POLYMERS,
        200,
        500,
        MaterialUnit.TONNE,
        purity=92,
        moisture=1,
        contamination=2.0,
        distance=250,
        hazards=["toxic"],
        price=340,
        description="Hot-washed PET flake for thermoformed packaging.",
    ),
    _demand(
        "northgate-packaging",
        "Recycled fibre for board",
        MaterialCategory.PAPER,
        400,
        1200,
        MaterialUnit.TONNE,
        purity=85,
        moisture=12,
        contamination=3.0,
        distance=300,
        price=95,
        description="Recovered fibre for corrugated board.",
    ),
    _demand(
        "northgate-packaging",
        "Polyolefin film resin",
        MaterialCategory.POLYMERS,
        150,
        600,
        MaterialUnit.TONNE,
        purity=85,
        moisture=2,
        contamination=4.0,
        distance=250,
        price=280,
        description="Post-industrial polyolefin for film extrusion.",
    ),
    _demand(
        "northgate-packaging",
        "Recycled cotton fibre for protective packaging",
        MaterialCategory.TEXTILES,
        40,
        150,
        MaterialUnit.TONNE,
        purity=90,
        contamination=2.0,
        distance=250,
        price=150,
        description="Cotton fibre for moulded protective packaging.",
    ),
    _demand(
        "brightfield-energy",
        "Waste-derived biomass fuel",
        MaterialCategory.ENERGY,
        500,
        2500,
        MaterialUnit.TONNE,
        purity=80,
        moisture=35,
        contamination=3.0,
        distance=400,
        hazards=["oxidising"],
        price=42,
        description="Co-firing fuel; moisture above limit requires drying.",
    ),
    _demand(
        "brightfield-energy",
        "Process water for cooling makeup",
        MaterialCategory.WATER,
        200,
        2000,
        MaterialUnit.CUBIC_METRE,
        purity=90,
        contamination=2.0,
        distance=300,
        price=1.8,
        description="Cooling tower makeup water, continuous demand.",
    ),
    _demand(
        "aurelia-chemicals",
        "Bio-based feedstock for fermentation",
        MaterialCategory.CHEMICALS,
        100,
        800,
        MaterialUnit.TONNE,
        purity=85,
        moisture=60,
        contamination=2.5,
        distance=500,
        hazards=["toxic"],
        price=70,
        description="Fermentation carbon source from organic secondary streams.",
    ),
    _demand(
        "meridian-steel",
        "Recovered acid for pickling line",
        MaterialCategory.CHEMICALS,
        100,
        400,
        MaterialUnit.TONNE,
        purity=70,
        moisture=20,
        contamination=6.0,
        distance=200,
        hazards=["flammable"],
        price=45,
        description="Spent acid reconditioned for the pickling line.",
    ),
    _demand(
        "aqualoop-utilities",
        "Off-spec ethanol as carbon source",
        MaterialCategory.CHEMICALS,
        50,
        300,
        MaterialUnit.CUBIC_METRE,
        purity=85,
        moisture=15,
        contamination=5.0,
        distance=300,
        price=210,
        description="Ethanol as denitrification carbon source.",
    ),
    _demand(
        "terranova-foods",
        "Secondary packaging film",
        MaterialCategory.POLYMERS,
        20,
        80,
        MaterialUnit.TONNE,
        purity=80,
        moisture=3,
        contamination=5.0,
        distance=200,
        price=190,
        frequency=DemandFrequency.MONTHLY,
        description="Post-industrial film for secondary packaging.",
    ),
    _demand(
        "circulus-glass",
        "Cullet for container glass",
        MaterialCategory.GLASS,
        300,
        1500,
        MaterialUnit.TONNE,
        purity=92,
        moisture=1,
        contamination=2.0,
        distance=200,
        price=105,
        description="High-purity colour-sorted cullet for container glass.",
    ),
]


DEMO_PROPOSALS: list[dict] = [
    {
        "material": "LM-0004",
        "demand": "Cement kiln slag feedstock",
        "quantity": 2500,
        "status": ProposalStatus.APPROVED,
        "price": 18,
        "transaction": {
            "status": TransactionStatus.VERIFIED,
            "accepted_quantity": 2500,
            "verified_quantity": 2410,
            "distance_km": 132.4,
            "carrier": "Demo Bulk Logistics",
            "method": VerificationMethod.WEIGHBRIDGE_TICKET,
            "dispatched_days_ago": 9,
            "delivered_days_ago": 6,
            "verified_days_ago": 5,
            "evidence": {
                "weighbridge_ticket": "DEMO-WB-2026-0412",
                "ticket_mass_kg": 2_410_000,
                "note": "Demo record — not a real delivery.",
            },
        },
    },
    {
        "material": "LM-0007",
        "demand": "Recycled PET flake",
        "quantity": 320,
        "status": ProposalStatus.APPROVED,
        "price": 340,
        "transaction": {
            "status": TransactionStatus.TRANSFERRED,
            "accepted_quantity": 320,
            "distance_km": 96.8,
            "carrier": "Demo Regional Freight",
            "dispatched_days_ago": 2,
            "delivered_days_ago": 1,
            "evidence": {"delivery_note": "DEMO-DN-8841"},
        },
    },
    {
        "material": "LM-0001",
        "demand": "Recovered acid for pickling line",
        "quantity": 180,
        "status": ProposalStatus.APPROVED,
        "price": 45,
        "transaction": {
            "status": TransactionStatus.CREATED,
            "accepted_quantity": 180,
            "distance_km": 148.2,
            "carrier": "Demo Hazmat Transport",
            "evidence": {"consignment": "DEMO-CN-2207"},
        },
    },
    {
        "material": "LM-0015",
        "demand": "Glass cullet aggregate substitute",
        "quantity": 900,
        "status": ProposalStatus.SUBMITTED,
        "price": 12,
    },
    {
        "material": "LM-0013",
        "demand": "Recycled cotton fibre for protective packaging",
        "quantity": 60,
        "status": ProposalStatus.UNDER_REVIEW,
        "price": 150,
    },
    {
        "material": "LM-0010",
        "demand": "Bio-based feedstock for fermentation",
        "quantity": 400,
        "status": ProposalStatus.SUBMITTED,
        "price": 70,
    },
    {
        # Draft proposal against a pair the engine accepts as conditional
        # (organic stream substituted into chemical feedstock).
        "material": "LM-0012",
        "demand": "Bio-based feedstock for fermentation",
        "quantity": 120,
        "status": ProposalStatus.DRAFT,
        "price": 70,
    },
]


def _proposal_lifecycle_fields(status: ProposalStatus) -> dict:
    """Lifecycle evidence for a seeded proposal in the given state.

    Demo provenance is explicit: the actors are demo identities and every
    approval carries a DEMO- reference so no seeded record can be mistaken for
    a real decision.
    """
    fields: dict = {"version": 0}
    if status == ProposalStatus.DRAFT:
        return fields
    fields["submitted_by"] = "aurelia-coordinator"
    fields["submitted_at"] = NOW - timedelta(days=6)
    if status in {
        ProposalStatus.APPROVED,
        ProposalStatus.IN_PROGRESS,
        ProposalStatus.COMPLETED,
    }:
        fields["reviewed_by"] = "helios-approver"
        fields["reviewed_at"] = NOW - timedelta(days=5)
        fields["approved_by"] = "helios-approver"
        fields["approved_at"] = NOW - timedelta(days=4)
        fields["approval_reference"] = "DEMO-APPR-2026-0007"
        fields["approval_evidence"] = {
            "source": "demo",
            "decision": "approved",
            "note": "Demo approval record — not a real decision.",
        }
    return fields


def _seed_transition_history(session: Session) -> None:
    """Write the transition history and audit trail implied by seeded states.

    Seeded records must not appear to have transitioned through the workflow
    without a history: the detail view and audit timeline read these rows.
    """
    from app.db.enums import ActorRole, AuditSeverity, TransitionEntity
    from app.db.models.transition import StatusTransition

    actors = {
        "submit": ("aurelia-coordinator", ActorRole.COORDINATOR),
        "review": ("helios-approver", ActorRole.REVIEWER),
        "approve": ("helios-approver", ActorRole.APPROVER),
        "start": ("aurelia-coordinator", ActorRole.COORDINATOR),
        "complete": ("northgate-auditor", ActorRole.AUDITOR),
        "record_transfer": ("aurelia-coordinator", ActorRole.COORDINATOR),
        "verify": ("northgate-auditor", ActorRole.AUDITOR),
    }

    for proposal in session.scalars(select(RecoveryProposal)).all():
        if proposal.status == ProposalStatus.DRAFT:
            continue

        steps: list[tuple[str, str, str, int]] = [("submit", "draft", "submitted", 6)]
        if proposal.status in {
            ProposalStatus.UNDER_REVIEW,
            ProposalStatus.APPROVED,
            ProposalStatus.IN_PROGRESS,
            ProposalStatus.COMPLETED,
        }:
            steps.append(("review", "submitted", "under_review", 5))
        if proposal.status in {
            ProposalStatus.APPROVED,
            ProposalStatus.IN_PROGRESS,
            ProposalStatus.COMPLETED,
        }:
            steps.append(("approve", "under_review", "approved", 4))

        transaction = proposal.transaction
        if transaction is not None:
            steps.append(("start", "approved", "in_progress", 3))
            if transaction.status in {
                TransactionStatus.TRANSFERRED,
                TransactionStatus.VERIFIED,
            }:
                steps.append(("record_transfer", "created", "transferred", 2))
            if transaction.status == TransactionStatus.VERIFIED:
                steps.append(("complete", "in_progress", "completed", 1))

        for action, from_state, to_state, days_ago in steps:
            actor_id, role = actors[action]
            occurred = NOW - timedelta(days=days_ago)
            entity_type = (
                TransitionEntity.TRANSACTION
                if action == "record_transfer"
                else TransitionEntity.PROPOSAL
            )
            entity_id = transaction.id if entity_type == TransitionEntity.TRANSACTION else proposal.id
            session.add(
                StatusTransition(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    action=action,
                    from_state=from_state,
                    to_state=to_state,
                    actor_id=actor_id,
                    actor_role=role,
                    organization_id=proposal.proposed_by_organization_id,
                    reason=None,
                    context={"demo": True},
                    occurred_at=occurred,
                )
            )
            audit.record_event(
                session,
                event_type=f"{entity_type.value}.{action}",
                entity_type=entity_type.value,
                entity_id=entity_id,
                previous_state=from_state,
                new_state=to_state,
                actor=actor_id,
                actor_id=actor_id,
                organization_id=proposal.proposed_by_organization_id,
                severity=AuditSeverity.INFO,
                summary=(
                    f"Demo {entity_type.value} {from_state} → {to_state} ({action})."
                ),
                payload={"demo": True, "action": action},
                created_at=occurred,
                updated_at=occurred,
            )


def _clear(session: Session) -> None:
    from app.db.models.transition import StatusTransition

    for model in (
        StatusTransition,
        RecoveryTransaction,
        RecoveryProposal,
        RecoveryOpportunity,
        MaterialSpecification,
        Material,
        ResourceDemand,
        AgentExecution,
        AuditEvent,
        AuditIntegrityState,
        Organization,
    ):
        session.execute(delete(model))
    session.commit()


def seed_demo(session: Session, *, reset: bool = False) -> dict:
    if settings.is_production:
        raise SystemExit("Refusing to load demo data while ENVIRONMENT=production.")

    if reset:
        _clear(session)

    existing = session.scalar(select(func.count(Organization.id))) or 0
    if existing:
        return {
            "status": "skipped",
            "reason": "organizations already exist; pass --reset to reload the demo dataset",
            "organizations": existing,
        }

    organizations: dict[str, Organization] = {}
    for record in DEMO_ORGANIZATIONS:
        organization = Organization(
            **record,
            data_source=DataSource.DEMO,
            is_demo=True,
        )
        session.add(organization)
        organizations[record["slug"]] = organization
    session.flush()

    materials: dict[str, Material] = {}
    for record in DEMO_MATERIALS:
        organization = organizations[record["org"]]
        material = Material(
            organization_id=organization.id,
            reference_code=record["ref"],
            name=record["name"],
            category=record["category"],
            description=record["description"],
            quantity_available=record["quantity"],
            unit=record["unit"],
            condition=record["condition"],
            status=MaterialStatus.AVAILABLE,
            hazard_class=record["hazard"],
            handling_requirements=record["handling"],
            origin_process=record["origin"],
            availability_start=TODAY - timedelta(days=30),
            # Must fully cover the 240-day demand horizon, otherwise every link
            # would be downgraded to 'conditional' by the timing rule.
            availability_end=TODAY + timedelta(days=300),
            data_source=DataSource.DEMO,
            is_demo=True,
        )
        session.add(material)
        session.flush()
        if record["spec"]:
            spec = record["spec"]
            session.add(
                MaterialSpecification(
                    material_id=material.id,
                    purity_pct=spec.get("purity_pct"),
                    moisture_pct=spec.get("moisture_pct"),
                    contamination_pct=spec.get("contamination_pct"),
                    ph_value=spec.get("ph_value"),
                    calorific_value_mj_kg=spec.get("calorific_value_mj_kg"),
                    particle_size_mm=spec.get("particle_size_mm"),
                    composition=spec.get("composition", []),
                    contaminants=spec.get("contaminants", {}),
                    assay_method=spec.get("assay_method"),
                    notes=spec.get("notes"),
                )
            )
        materials[record["ref"]] = material

    demands: dict[str, ResourceDemand] = {}
    for record in DEMO_DEMANDS:
        organization = organizations[record["org"]]
        demand = ResourceDemand(
            organization_id=organization.id,
            title=record["title"],
            category=record["category"],
            description=record["description"],
            min_purity_pct=record["purity"],
            max_moisture_pct=record["moisture"],
            max_contamination_pct=record["contamination"],
            prohibited_hazards=record["hazards"],
            min_quantity=record["min_quantity"],
            max_quantity=record["max_quantity"],
            unit=record["unit"],
            frequency=record["frequency"],
            max_distance_km=record["distance"],
            needed_from=TODAY + timedelta(days=7),
            needed_until=TODAY + timedelta(days=240),
            max_price_per_unit=record["price"],
            currency="EUR",
            status=DemandStatus.OPEN,
            data_source=DataSource.DEMO,
            is_demo=True,
        )
        session.add(demand)
        demands[record["title"]] = demand

    session.commit()

    discovery_summary = discover_opportunities(session, actor="seed")

    opportunities = {
        (opportunity.material_id, opportunity.resource_demand_id): opportunity
        for opportunity in session.scalars(select(RecoveryOpportunity)).all()
    }

    proposals_created = 0
    for record in DEMO_PROPOSALS:
        material = materials[record["material"]]
        demand = demands[record["demand"]]
        opportunity = opportunities.get((material.id, demand.id))
        if opportunity is None:
            # Never persist a proposal for a pair the engine rejected.
            print(
                f"skipped demo proposal: no opportunity for {record['material']} "
                f"-> {record['demand']}",
                file=sys.stderr,
            )
            continue

        proposal = RecoveryProposal(
            opportunity_id=opportunity.id,
            proposed_by_organization_id=opportunity.supplier_organization_id,
            receiving_organization_id=opportunity.consumer_organization_id,
            quantity=record["quantity"],
            unit=opportunity.unit,
            price_per_unit=record["price"],
            currency="EUR",
            status=record["status"],
            compatibility_status=opportunity.compatibility_status,
            terms={
                "incoterm": "EXW",
                "inspection": "incoming inspection by receiver",
                "demo": True,
            },
            valid_until=NOW + timedelta(days=30),
            notes="Demo proposal generated for the LOOPMESH hackathon build.",
            is_demo=True,
            **_proposal_lifecycle_fields(record["status"]),
        )
        session.add(proposal)
        session.flush()
        proposals_created += 1

        transaction_record = record.get("transaction")
        if transaction_record:
            verified_at = (
                _days(transaction_record["verified_days_ago"])
                if transaction_record.get("verified_days_ago") is not None
                else None
            )
            delivered_at = (
                _days(transaction_record["delivered_days_ago"])
                if transaction_record.get("delivered_days_ago") is not None
                else None
            )
            transaction_status = transaction_record["status"]
            transferred = transaction_status in {
                TransactionStatus.TRANSFERRED,
                TransactionStatus.VERIFIED,
            }
            transfer_evidence = transaction_record.get("evidence") or {}
            transfer_fields = (
                {
                    "transferred_quantity": transaction_record.get("accepted_quantity"),
                    "transferred_at": delivered_at or verified_at or _days(1),
                    "transfer_recorded_by": "aurelia-coordinator",
                    "transfer_reference": (
                        transfer_evidence.get("weighbridge_ticket")
                        or transfer_evidence.get("delivery_note")
                        or "DEMO-TRANSFER-REF"
                    ),
                    "material_identification": f"{material.name} (demo batch)",
                }
                if transferred
                else {}
            )
            transaction = RecoveryTransaction(
                proposal_id=proposal.id,
                status=transaction_status,
                source_organization_id=proposal.proposed_by_organization_id,
                destination_organization_id=proposal.receiving_organization_id,
                accepted_quantity=transaction_record.get("accepted_quantity"),
                verified_quantity=transaction_record.get("verified_quantity"),
                unit=opportunity.unit,
                transport_distance_km=transaction_record.get("distance_km"),
                carrier_name=transaction_record.get("carrier"),
                dispatched_at=(
                    _days(transaction_record["dispatched_days_ago"])
                    if transaction_record.get("dispatched_days_ago") is not None
                    else None
                ),
                delivered_at=delivered_at,
                verified_at=verified_at,
                verified_by="northgate-auditor" if verified_at else None,
                verification_method=transaction_record.get("method"),
                evidence=transaction_record.get("evidence", {}),
                notes="Demo transaction record — no real material movement occurred.",
                is_demo=True,
                version=1 if transferred else 0,
                **transfer_fields,
            )
            session.add(transaction)
            opportunity.status = OpportunityStatus.CONVERTED
        elif record["status"] in {ProposalStatus.SUBMITTED, ProposalStatus.UNDER_REVIEW}:
            opportunity.status = OpportunityStatus.SHORTLISTED

    _seed_transition_history(session)
    session.commit()

    dataset_summary = {
        "organizations": len(DEMO_ORGANIZATIONS),
        "materials": len(DEMO_MATERIALS),
        "demands": len(DEMO_DEMANDS),
        "opportunities": len(opportunities),
        "proposals": proposals_created,
        "discovery": discovery_summary.as_dict(),
        "verified_transactions": 1,
        "demo": True,
    }

    audit.record_event(
        session,
        event_type="seed.demo_loaded",
        entity_type="organization",
        actor="seed",
        summary="Demo industrial cluster loaded: 12 organisations, 21 streams, 16 demands.",
        payload={**dataset_summary, "demo": True},
    )
    audit.record_event(
        session,
        event_type="material.registered",
        entity_type="material",
        entity_id=materials["LM-0004"].id,
        actor="meridian-steel",
        summary="Blast furnace slag registered with a full assay and handling profile.",
        payload={"demo": True, "reference_code": "LM-0004"},
    )
    audit.record_event(
        session,
        event_type="discovery.run",
        entity_type="recovery_opportunity",
        actor="seed",
        summary=(
            f"Deterministic discovery evaluated "
            f"{discovery_summary.pairs_evaluated} pairs and kept "
            f"{discovery_summary.opportunities_created} feasible links."
        ),
        payload={"demo": True, **discovery_summary.as_dict()},
    )
    audit.record_event(
        session,
        event_type="proposal.submitted",
        entity_type="recovery_proposal",
        actor="aurelia-chemicals",
        summary="Recovered acid proposal submitted for the Meridian pickling line.",
        payload={"demo": True},
    )
    audit.record_event(
        session,
        event_type="transaction.verified",
        entity_type="recovery_transaction",
        actor="helios-cement",
        summary=(
            "2410 t of slag verified against a weighbridge ticket (demo evidence, "
            "not a real environmental claim)."
        ),
        severity="info",
        payload={"demo": True, "verified_quantity": 2410, "unit": "tonne"},
    )

    # Space the journal entries out so the activity feed reads like a timeline.
    events = list(
        session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc())).all()
    )
    offsets = [0, 1, 3, 5, 8, 12]
    for index, event in enumerate(reversed(events)):
        event.created_at = _days(offsets[index % len(offsets)])
        event.updated_at = event.created_at

    session.commit()

    return {
        "status": "seeded",
        **dataset_summary,
        "accounting": "Only the verified 2410 t (demo) counts as recovered material.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Load the LOOPMESH demo dataset.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing LOOPMESH rows before loading the demo dataset.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        summary = seed_demo(session, reset=args.reset)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
