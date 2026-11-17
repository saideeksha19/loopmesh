"""Verify protected demo databases against backend/db_baseline.json.

Usage:
    python scripts/verify_database_integrity.py
    python scripts/verify_database_integrity.py --json

This is deliberately read-only.  To update the baseline after an approved demo
database change, run with --write --approval-reference <ticket>.  Never run
--write just to make a failing check green.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.db_integrity import compare, inspect_database  # noqa: E402

DEFAULT_BASELINE = BACKEND / "db_baseline.json"
PROTECTED = ("loopmesh_dev.db", "loopmesh_e2e.db")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--approval-reference", default="")
    args = parser.parse_args()

    if args.write and not args.approval_reference.strip():
        print("Refusing to update baseline without --approval-reference.", file=sys.stderr)
        return 2

    actual = {
        name: inspect_database(BACKEND / name)
        for name in PROTECTED
        if (BACKEND / name).is_file()
    }
    if args.write:
        baseline = {
            "version": 1,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "approval_reference": args.approval_reference,
            "databases": actual,
            "notes": (
                "Protected demo databases. Tests must use disposable copies. "
                "Update only after an approved, recorded demo data change."
            ),
        }
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.baseline} for {len(actual)} database(s).")
        return 0

    if not args.baseline.is_file():
        print(f"Baseline missing: {args.baseline}", file=sys.stderr)
        return 1
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    expected = baseline.get("databases", {})
    problems: dict[str, list[str]] = {}
    for name in PROTECTED:
        if name not in expected:
            problems[name] = ["database is present in the repository but absent from the baseline"]
            continue
        if name not in actual:
            problems[name] = ["baseline exists but the protected database is missing"]
            continue
        found = compare(actual[name], expected[name])
        if found:
            problems[name] = found

    output = {
        "ok": not problems,
        "baseline": str(args.baseline),
        "checked": sorted(actual),
        "problems": problems,
        "databases": {
            name: {
                "sha256": info["sha256"],
                "schema_fingerprint": info["schema_fingerprint"],
                "alembic_revision": info["alembic_revision"],
                "integrity_check": info["integrity_check"],
            }
            for name, info in actual.items()
        },
    }
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        if problems:
            print("DEMO DATABASE BASELINE FAILED")
            for name, reasons in problems.items():
                for reason in reasons:
                    print(f"  {name}: {reason}")
        else:
            print("Demo database baseline OK")
            for name, info in actual.items():
                print(
                    f"  {name}: {info['sha256']} schema={info['schema_fingerprint'][:16]} "
                    f"alembic={info['alembic_revision']}"
                )
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
