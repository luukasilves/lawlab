"""Apply the checked-in Lawlab database schema."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import config  # noqa: F401  # loads .env as a side effect


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply db/schema.sql to Postgres.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read schema.sql and report its size without connecting.",
    )
    args = parser.parse_args()

    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    if args.dry_run:
        print(f"Read {SCHEMA_PATH} ({len(schema.encode('utf-8'))} bytes). Dry run only.")
        return 0

    dsn = os.getenv("SUPABASE_DB_POOLER_URL")
    if not dsn:
        print("SUPABASE_DB_POOLER_URL is not set; cannot apply db/schema.sql.")
        return 2

    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()

    print(f"Applied {SCHEMA_PATH} successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
