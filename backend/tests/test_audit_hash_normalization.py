"""Focused Batch 13 regression: audit hash timestamp normalization."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.audit_integrity import (
    GENESIS_HASH,
    as_utc,
    audit_event_hash,
    canonical_json,
    timestamp_text,
)
from app.db.base import Base, utcnow
from app.db.enums import AuditSeverity
from app.services import audit as audit_service


def _event(**overrides):
    base = {
        "integrity_sequence": 1,
        "id": uuid.UUID("57940700-f801-48e3-8ff0-075e9b78afb6"),
        "event_type": "auth.login_succeeded",
        "entity_type": "user",
        "entity_id": uuid.UUID("e336fcbe-244a-4c0d-b376-fcb9786c97f1"),
        "previous_state": None,
        "new_state": None,
        "actor": "e336fcbe-244a-4c0d-b376-fcb9786c97f1",
        "actor_id": "e336fcbe-244a-4c0d-b376-fcb9786c97f1",
        "organization_id": None,
        "severity": AuditSeverity.INFO,
        "summary": "User signed in.",
        "reason": None,
        "detail": None,
        "payload": {"session_id": "3bd02754-c565-4fa6-9454-3b99363b6625"},
        "created_at": datetime(2026, 11, 16, 8, 21, 56, 150818, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 11, 16, 8, 21, 56, 150818, tzinfo=timezone.utc),
        "previous_hash": GENESIS_HASH,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# unit: normalization and hashing primitives
# ---------------------------------------------------------------------------


def test_utc_aware_datetime_normalization():
    value = datetime(2026, 11, 16, 8, 21, 56, 150818, tzinfo=timezone.utc)
    assert as_utc(value) == value
    assert timestamp_text(value) == "2026-11-16T08:21:56.150818+00:00"


def test_non_utc_aware_datetime_normalization():
    ist = timezone(timedelta(hours=5, minutes=30))
    value = datetime(2026, 11, 16, 13, 51, 56, 150818, tzinfo=ist)
    normalized = as_utc(value)
    assert normalized.tzinfo == timezone.utc
    assert normalized == datetime(2026, 11, 16, 8, 21, 56, 150818, tzinfo=timezone.utc)
    assert timestamp_text(value) == "2026-11-16T08:21:56.150818+00:00"


def test_equivalent_instants_with_different_offsets_produce_identical_timestamp_strings():
    utc_value = datetime(2026, 11, 16, 8, 21, 56, 150818, tzinfo=timezone.utc)
    ist_value = datetime(2026, 11, 16, 13, 51, 56, 150818, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    est_value = datetime(2026, 11, 16, 3, 21, 56, 150818, tzinfo=timezone(timedelta(hours=-5)))
    assert timestamp_text(utc_value) == timestamp_text(ist_value) == timestamp_text(est_value)
    assert timestamp_text(ist_value) == "2026-11-16T08:21:56.150818+00:00"


def test_equivalent_instants_produce_identical_audit_hashes():
    utc_event = _event()
    ist = timezone(timedelta(hours=5, minutes=30))
    ist_event = _event(
        created_at=datetime(2026, 11, 16, 13, 51, 56, 150818, tzinfo=ist),
        updated_at=datetime(2026, 11, 16, 13, 51, 56, 150818, tzinfo=ist),
    )
    assert audit_event_hash(utc_event) == audit_event_hash(ist_event)
    # Matches the stored hash observed for this logical event (UTC-sealed).
    assert audit_event_hash(ist_event) == "5b0dccac218b323a035df7b6704ce06108a7cbdae4572f1487f5822546bdff91"


def test_naive_datetime_behavior_follows_existing_contract():
    naive = datetime(2026, 11, 16, 8, 21, 56, 150818)
    normalized = as_utc(naive)
    assert normalized.tzinfo == timezone.utc
    assert normalized == datetime(2026, 11, 16, 8, 21, 56, 150818, tzinfo=timezone.utc)
    assert timestamp_text(naive) == "2026-11-16T08:21:56.150818+00:00"


def test_json_payload_canonicalization_unchanged():
    payload_a = {"b": 1, "a": {"y": 2, "x": 1}}
    payload_b = {"a": {"x": 1, "y": 2}, "b": 1}
    e1 = _event(payload=payload_a)
    e2 = _event(payload=payload_b)
    assert canonical_json(payload_a) == canonical_json(payload_b)
    assert audit_event_hash(e1) == audit_event_hash(e2)


def test_updated_at_is_included_consistently_in_hash_material():
    e1 = _event(updated_at=datetime(2026, 11, 16, 8, 21, 56, 150818, tzinfo=timezone.utc))
    e2 = _event(updated_at=datetime(2026, 11, 16, 8, 21, 57, 150818, tzinfo=timezone.utc))
    assert audit_event_hash(e1) != audit_event_hash(e2)


# ---------------------------------------------------------------------------
# SQLite regression: append/verify and chain continuity
# ---------------------------------------------------------------------------


def _sqlite_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'audit.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return engine, factory()


def test_sqlite_append_verify_and_multiple_events_preserve_chain(tmp_path: Path):
    engine, session = _sqlite_session(tmp_path)
    try:
        events = []
        for i in range(5):
            events.append(
                audit_service.record_event(
                    session,
                    event_type="test.chain",
                    entity_type="test",
                    summary=f"event {i}",
                    payload={"i": i, "k": "v"},
                )
            )
        session.commit()
        result = audit_service.verify_integrity(session, batch_size=2)
        assert result["valid"] is True
        assert result["checked"] == 5
        assert result["reason"] is None
        # chain continuity
        assert events[0].previous_hash == GENESIS_HASH
        for prev, cur in zip(events, events[1:]):
            assert cur.previous_hash == prev.event_hash
            assert cur.integrity_sequence == prev.integrity_sequence + 1
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# PostgreSQL integration (existing disposable cluster/dbs, no record mutation)
# ---------------------------------------------------------------------------


PG_URL = os.environ.get(
    "LOOPMESH_PG_URL",
    "postgresql+psycopg://loopmesh@127.0.0.1:55433/loopmesh_batch13",
)


def _pg_available(url: str) -> bool:
    # This probe runs at import time (inside skipif decorators), so it must never
    # block: without an explicit connect_timeout libpq waits on TCP for minutes
    # when nothing is listening, stalling collection before any test runs.
    connect_args = {"connect_timeout": 2} if url.startswith("postgresql") else {}
    try:
        eng = create_engine(url, future=True, connect_args=connect_args)
        with eng.connect() as c:
            c.execute(text("select 1"))
        eng.dispose()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _pg_available(PG_URL), reason="disposable PostgreSQL not available")
def test_postgresql_non_utc_session_append_read_verify_and_chain_continuity():
    engine = create_engine(PG_URL, future=True)
    # Append in a non-UTC session timezone; record_event seals UTC timestamps.
    with Session(engine) as session:
        session.execute(text("set time zone 'Asia/Calcutta'"))
        before = audit_service.verify_integrity(session, batch_size=500)
        before_state_seq = before["state_sequence"]
        start_count = before["checked"]
        e1 = audit_service.record_event(
            session,
            event_type="test.pg.norm",
            entity_type="test",
            summary="pg normalization 1",
            payload={"x": 1},
        )
        e2 = audit_service.record_event(
            session,
            event_type="test.pg.norm",
            entity_type="test",
            summary="pg normalization 2",
            payload={"x": 2},
        )
        session.commit()
        ids = [e1.id, e2.id]

    # Read back in non-UTC session; timestamps come back as session-local aware.
    with Session(engine) as session:
        session.execute(text("set time zone 'Asia/Calcutta'"))
        rows = session.execute(
            text(
                "select created_at, updated_at from audit_events "
                "where id = :id1 or id = :id2 order by integrity_sequence"
            ),
            {"id1": ids[0], "id2": ids[1]},
        ).fetchall()
        assert len(rows) == 2
        for created_at, updated_at in rows:
            assert created_at.tzinfo is not None and updated_at.tzinfo is not None
            assert timestamp_text(created_at).endswith("+00:00")
            assert timestamp_text(updated_at).endswith("+00:00")
        result = audit_service.verify_integrity(session, batch_size=100)
        assert result["valid"] is True, result
        assert result["reason"] is None
        assert result["checked"] == start_count + 2
        assert result["state_sequence"] == before_state_seq + 2
    engine.dispose()


@pytest.mark.skipif(not _pg_available(PG_URL), reason="disposable PostgreSQL not available")
def test_postgresql_verify_existing_source_and_restored_chains_without_altering_records():
    # Verify chains in-place; do not update/delete/regenerate any audit records.
    urls = [
        PG_URL,
        "postgresql+psycopg://loopmesh@127.0.0.1:55433/loopmesh_batch13_restore",
    ]
    for url in urls:
        if not _pg_available(url):
            pytest.skip(f"database not available: {url.rsplit('/', 1)[-1]}")
        engine = create_engine(url, future=True)
        try:
            with Session(engine) as session:
                session.execute(text("set time zone 'Asia/Calcutta'"))
                pre = session.execute(
                    text(
                        "select count(*), max(integrity_sequence), min(integrity_sequence) "
                        "from audit_events"
                    )
                ).one()
                pre_state = session.execute(
                    text("select last_sequence, last_hash from audit_integrity_state where id=1")
                ).one()
                result = audit_service.verify_integrity(session, batch_size=500)
                assert result["valid"] is True, (url, result)
                assert result["reason"] is None
                assert result["checked"] == pre_state[0]
                post = session.execute(
                    text(
                        "select count(*), max(integrity_sequence), min(integrity_sequence) "
                        "from audit_events"
                    )
                ).one()
                post_state = session.execute(
                    text("select last_sequence, last_hash from audit_integrity_state where id=1")
                ).one()
                assert pre == post
                assert pre_state == post_state
        finally:
            engine.dispose()
