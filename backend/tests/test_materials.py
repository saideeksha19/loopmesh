"""Material endpoints and CSV import tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import MaterialCategory
from tests.conftest import add_specification, make_material, make_organization

PLATFORM = {"X-Actor-Id": "demo-platform-admin"}


def material_payload(organization_id: str, **overrides) -> dict:
    payload = {
        "organization_id": organization_id,
        "reference_code": "LM-API-001",
        "name": "Pickling line sludge",
        "category": "metals",
        "quantity_available": 120.5,
        "unit": "tonne",
        "condition": "as_generated",
        "hazard_class": "non_hazardous",
        "handling_requirements": "Covered skips.",
        "availability_start": "2026-01-01",
        "availability_end": "2026-12-31",
        "specification": {
            "purity_pct": 88.5,
            "contamination_pct": 1.4,
            "moisture_pct": 3.2,
            "composition": [{"substance": "Fe2O3", "pct": 88.5}],
            "contaminants": {"Oil": 1.4},
        },
    }
    payload.update(overrides)
    return payload


def test_register_material_returns_created_profile(client: TestClient, db: Session) -> None:
    organization = make_organization(db)
    response = client.post(
        "/api/v1/materials", json=material_payload(str(organization.id)), headers=PLATFORM
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reference_code"] == "LM-API-001"
    assert body["category"] == "metals"
    assert body["quantity_available"] == 120.5
    assert body["specification"]["purity_pct"] == 88.5
    assert body["data_source"] == "form"
    assert body["is_demo"] is False


def test_duplicate_reference_code_is_rejected(client: TestClient, db: Session) -> None:
    organization = make_organization(db)
    payload = material_payload(str(organization.id))
    assert client.post("/api/v1/materials", json=payload, headers=PLATFORM).status_code == 201
    duplicate = client.post("/api/v1/materials", json=payload, headers=PLATFORM)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


def test_invalid_payload_returns_structured_validation_error(
    client: TestClient, db: Session
) -> None:
    organization = make_organization(db)
    response = client.post(
        "/api/v1/materials",
        json=material_payload(str(organization.id), quantity_available=-5),
        headers=PLATFORM,
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any("quantity_available" in field["location"] for field in error["details"]["fields"])


def test_unknown_organization_returns_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/v1/materials",
        json=material_payload("00000000-0000-0000-0000-000000000000"),
        headers=PLATFORM,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_materials_filters_by_category(client: TestClient, db: Session) -> None:
    supplier = make_organization(db)
    metals = make_material(db, supplier, name="Metals stream")
    add_specification(db, metals)
    make_material(db, supplier, name="Polymer stream", category=MaterialCategory.POLYMERS)
    db.commit()

    response = client.get("/api/v1/materials", params={"category": "metals"}, headers=PLATFORM)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Metals stream"
    assert body["items"][0]["organization"]["id"] == str(supplier.id)


def test_material_detail_includes_specification_and_404(client: TestClient, db: Session) -> None:
    organization = make_organization(db)
    material = make_material(db, organization)
    add_specification(db, material, purity=91.0)
    db.commit()

    found = client.get(f"/api/v1/materials/{material.id}", headers=PLATFORM)
    assert found.status_code == 200
    assert found.json()["specification"]["purity_pct"] == 91.0

    missing = client.get("/api/v1/materials/11111111-1111-1111-1111-111111111111", headers=PLATFORM)
    assert missing.status_code == 404


CSV_HEADER = (
    "organization_slug,reference_code,name,category,unit,quantity_available,"
    "condition,hazard_class,purity_pct,moisture_pct,contamination_pct,"
    "availability_start,availability_end\n"
)


def test_csv_import_reports_row_level_errors(client: TestClient, db: Session) -> None:
    organization = make_organization(db, slug="demo-import-org")
    db.commit()

    content = CSV_HEADER + (
        "demo-import-org,LM-CSV-001,Imported slag,minerals,tonne,500,processed,non_hazardous,"
        "94,8,0.6,2026-02-01,2026-12-31\n"
        "demo-import-org,LM-CSV-002,Imported cullet,glass,tonne,320,processed,non_hazardous,"
        "90,1,5.5,2026-02-01,2026-12-31\n"
        "unknown-org,LM-CSV-003,Bad row,glass,tonne,10,processed,non_hazardous,,,,,\n"
    )
    response = client.post(
        "/api/v1/materials/import",
        files={"file": ("materials.csv", content, "text/csv")},
        headers=PLATFORM,
    )
    assert response.status_code in {200, 201}, response.text
    body = response.json()
    assert body["rows_received"] == 3
    assert body["created"] == 2
    assert body["skipped"] == 1
    assert body["errors"][0]["row"] == 4
    assert "organization_slug" in body["errors"][0]["message"]

    listed = client.get(
        "/api/v1/materials", params={"organization_id": str(organization.id)}, headers=PLATFORM
    ).json()
    assert listed["total"] == 2


def test_csv_import_rejects_missing_columns(client: TestClient) -> None:
    response = client.post(
        "/api/v1/materials/import",
        files={"file": ("bad.csv", "name,category\nfoo,metals\n", "text/csv")},
        headers=PLATFORM,
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "import_rejected"
    assert "organization_slug" in error["details"]["missing_columns"]


def test_csv_import_rejects_non_csv_extension(client: TestClient) -> None:
    response = client.post(
        "/api/v1/materials/import",
        files={"file": ("data.txt", "not,a,csv\n", "text/plain")},
        headers=PLATFORM,
    )
    assert response.status_code == 422
