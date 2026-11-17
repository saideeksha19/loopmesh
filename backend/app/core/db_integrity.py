"""Read-only SQLite database baselines.

The protected demo databases are evidence in the Batch 13 report.  Everything
here opens them with ``mode=ro``; the verifier never migrates, vacuums, writes a
row or changes journal mode.  A byte hash detects any change, while the schema
fingerprint explains structural drift even when the file size is similar.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        {
            "name": row[1],
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5],
        }
        for row in conn.execute(f'PRAGMA table_info("{table}")')
    ]


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        {
            "id": row[0],
            "seq": row[1],
            "table": row[2],
            "from": row[3],
            "to": row[4],
            "on_update": row[5],
            "on_delete": row[6],
        }
        for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')
    ]


def _indexes(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in conn.execute(f'PRAGMA index_list("{table}")'):
        name = row[1]
        result.append(
            {
                "name": name,
                "unique": row[2],
                "origin": row[3],
                "partial": row[4],
                "columns": [
                    {"seqno": info[0], "cid": info[1], "name": info[2]}
                    for info in conn.execute(f'PRAGMA index_info("{name}")')
                ],
            }
        )
    return sorted(result, key=lambda item: item["name"])


def schema_fingerprint(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    schema: dict[str, Any] = {}
    for table in tables:
        schema[table] = {
            "columns": _columns(conn, table),
            "foreign_keys": _foreign_keys(conn, table),
            "indexes": _indexes(conn, table),
        }
    material = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest(), schema


def inspect_database(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchall()
        revision_rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        fingerprint, schema = schema_fingerprint(conn)
        tables = sorted(schema)
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "schema_fingerprint": fingerprint,
            "table_count": len(tables),
            "tables": tables,
            "alembic_revision": revision_rows[0][0] if revision_rows else None,
            "integrity_check": [row[0] for row in integrity],
        }
    finally:
        conn.close()


def compare(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in ("sha256", "schema_fingerprint", "alembic_revision"):
        if actual.get(key) != expected.get(key):
            problems.append(
                f"{key}: expected {expected.get(key)!r}, got {actual.get(key)!r}"
            )
    if actual.get("integrity_check") != ["ok"]:
        problems.append(f"SQLite integrity_check: {actual.get('integrity_check')!r}")
    return problems
