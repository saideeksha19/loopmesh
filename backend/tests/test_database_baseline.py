"""Batch 13: protected demo databases must not change silently."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.db_integrity import compare, inspect_database

BACKEND = Path(__file__).resolve().parents[1]
BASELINE = BACKEND / "db_baseline.json"
PROTECTED = ("loopmesh_dev.db", "loopmesh_e2e.db")


@pytest.mark.parametrize("name", PROTECTED)
def test_protected_demo_database_matches_baseline(name: str) -> None:
    database = BACKEND / name
    if not database.is_file():
        pytest.skip(f"{name} is not present in this checkout")
    if not BASELINE.is_file():
        pytest.fail("backend/db_baseline.json is required to protect demo databases")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    expected = baseline["databases"][name]
    actual = inspect_database(database)
    assert compare(actual, expected) == []
    assert actual["alembic_revision"] == expected["alembic_revision"]
    assert actual["integrity_check"] == ["ok"]


def test_baseline_is_read_only_and_has_both_databases() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert set(PROTECTED).issubset(baseline["databases"])
    for name in PROTECTED:
        info = baseline["databases"][name]
        assert len(info["sha256"]) == 64
        assert len(info["schema_fingerprint"]) == 64
        assert info["alembic_revision"]
