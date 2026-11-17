"""SQLite backup/restore helpers used by the Batch 13 recovery drill.

Production PostgreSQL backups use ``pg_dump -Fc`` and ``pg_restore``; the
runbook documents those commands.  These helpers provide a repeatable local
proof that a copy can be restored, retains its schema revision and still passes
audit-chain verification.  The source database is opened read-only.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from app.core.db_integrity import inspect_database, sha256_file


def backup_sqlite(source: Path | str, destination: Path | str) -> dict[str, str | int]:
    source_path = Path(source)
    target_path = Path(destination)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if target_path.exists():
        raise FileExistsError(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    source_conn = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    destination_conn = sqlite3.connect(target_path)
    try:
        source_conn.backup(destination_conn)
        destination_conn.commit()
    finally:
        destination_conn.close()
        source_conn.close()

    digest = sha256_file(target_path)
    sidecar = target_path.with_name(f"{target_path.name}.sha256")
    sidecar.write_text(f"{digest}  {target_path.name}\n", encoding="ascii")
    return {
        "source": str(source_path),
        "backup": str(target_path),
        "sha256": digest,
        "size_bytes": target_path.stat().st_size,
        "sidecar": str(sidecar),
    }


def restore_sqlite(backup: Path | str, destination: Path | str) -> dict[str, str | int]:
    backup_path = Path(backup)
    target_path = Path(destination)
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    if target_path.exists():
        raise FileExistsError(target_path)
    sidecar = backup_path.with_name(f"{backup_path.name}.sha256")
    if not sidecar.is_file():
        raise ValueError("backup checksum sidecar is missing")
    expected = sidecar.read_text(encoding="ascii").split()[0]
    actual = sha256_file(backup_path)
    if not _constant_time_text_equal(expected, actual):
        raise ValueError("backup checksum does not match its sidecar")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, target_path)
    info = inspect_database(target_path)
    if info["integrity_check"] != ["ok"]:
        target_path.unlink(missing_ok=True)
        raise ValueError(f"restored database failed integrity_check: {info['integrity_check']}")
    return {
        "restored": str(target_path),
        "sha256": info["sha256"],
        "alembic_revision": info["alembic_revision"] or "",
        "size_bytes": info["size_bytes"],
    }


def _constant_time_text_equal(left: str, right: str) -> bool:
    return hashlib.sha256(left.encode("ascii")).digest() == hashlib.sha256(
        right.encode("ascii")
    ).digest()
