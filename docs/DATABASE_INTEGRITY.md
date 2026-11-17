# Database Integrity Baseline (Batch 13)

The protected demo databases are evidence for the Batch 1–12 baseline and must
not change during Batch 13 testing or development validation.

## Protected files

- `backend/loopmesh_dev.db` (expected Alembic `c3e5f7a9b1d2`)
- `backend/loopmesh_e2e.db` (expected Alembic `c3e5f7a9b1d2`)

`backend/db_baseline.json` records, for each file:

- SHA-256 byte hash
- SQLite schema fingerprint (tables, columns, foreign keys, indexes)
- Alembic revision
- `PRAGMA integrity_check` result
- size and capture timestamp

## Read-only verification

From `backend/`:

```bash
.venv/Scripts/python.exe scripts/verify_database_integrity.py
.venv/Scripts/python.exe scripts/verify_database_integrity.py --json
```

The script opens each database with `file:<path>?mode=ro`, so it cannot write
rows, run migrations, vacuum or change journal state. It fails if the byte hash,
schema fingerprint, Alembic revision or SQLite integrity check differs from the
baseline.

Automated check: `backend/tests/test_database_baseline.py`.

## Intentionally updating the baseline

Only after an approved, recorded change to a protected demo database:

```bash
.venv/Scripts/python.exe scripts/verify_database_integrity.py --write --approval-reference <ticket-or-approval-id>
```

`--write` is refused without `--approval-reference`. Never update the baseline
to silence an unexpected test failure. Record the approval reference in the
change review and commit the updated `db_baseline.json` together with the
approved database change.

## Test and migration discipline

- Application tests use disposable SQLite databases (`sqlite://` / temp files).
- Alembic migrations must be validated on disposable copies.
- Backup/restore drills use disposable copies (`backend/tests/test_backup_restore.py`).
- `loopmesh_dev.db` and `loopmesh_e2e.db` are never migration targets for tests.
