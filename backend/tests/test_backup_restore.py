"""Batch 13 backup/restore and migration-backfill proof.

The source is a disposable, fully migrated SQLite database with synthetic audit
events.  No demo database is opened for writing and no secret is emitted.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.backup import backup_sqlite, restore_sqlite
from app.core.db_integrity import inspect_database
from app.services import audit

BACKEND = Path(__file__).resolve().parents[1]


def _alembic(database: Path, revision: str = "head") -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def _session(database: Path) -> Session:
    engine = create_engine(f"sqlite:///{database.as_posix()}", future=True)
    return Session(engine)


def test_backup_restore_preserves_schema_and_audit_chain(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    _alembic(source)

    with _session(source) as session:
        for index in range(5):
            audit.record_event(
                session,
                event_type="test.backup",
                entity_type="test",
                summary=f"synthetic event {index}",
            )
        session.commit()
        assert audit.verify_integrity(session)["valid"] is True

    result = backup_sqlite(source, backup)
    assert len(result["sha256"]) == 64
    assert inspect_database(backup)["integrity_check"] == ["ok"]

    restored_info = restore_sqlite(backup, restored)
    assert restored_info["alembic_revision"] == "e1c3a5b7d9f4"
    assert inspect_database(restored)["schema_fingerprint"] == inspect_database(source)[
        "schema_fingerprint"
    ]

    with _session(restored) as session:
        outcome = audit.verify_integrity(session)
        assert outcome["valid"] is True, outcome
        assert outcome["checked"] == 5


def test_restore_refuses_tampered_backup(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    _alembic(source)
    backup_sqlite(source, backup)
    with backup.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="checksum"):
        restore_sqlite(backup, tmp_path / "restored.db")


def test_batch13_migration_backfills_existing_audit_rows(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    _alembic(database, "d9a1c3e5b7f2")

    event_id = uuid.uuid4()
    conn = sqlite3.connect(database)
    try:
        conn.execute(
            "INSERT INTO audit_events "
            "(id, event_type, entity_type, entity_id, previous_state, new_state, actor, "
            "actor_id, organization_id, severity, summary, reason, detail, payload, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id.hex,
                "legacy.event",
                "test",
                None,
                None,
                None,
                "legacy-actor",
                "legacy-actor",
                None,
                "info",
                "pre-Batch-13 audit row",
                None,
                None,
                "{}",
                "2026-01-02 03:04:05.123456",
                "2026-01-02 03:04:05.123456",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _alembic(database, "head")
    with _session(database) as session:
        from app.db.models.audit import AuditEvent

        event = session.get(AuditEvent, event_id)
        assert event is not None
        assert event.integrity_sequence == 1
        assert len(event.event_hash or "") == 64
        assert audit.verify_integrity(session)["valid"] is True
