from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.database import configured_database_url, engine_for_url, ensure_reference_rows
from app.procurement import import_opportunities, parse_import


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OCDS JSON or flat OCDS CSV records into Arletion PostgreSQL.")
    parser.add_argument("file", type=Path, help="Path to an official OCDS JSON release package or CSV export.")
    parser.add_argument("--format", choices=("json", "csv"), required=True)
    args = parser.parse_args()
    url = configured_database_url()
    if not url:
        parser.error("DATABASE_URL is required")
    records = parse_import(args.file.read_text(encoding="utf-8-sig"), args.format)
    with sessionmaker(bind=engine_for_url(url), expire_on_commit=False)() as session:
        ensure_reference_rows(session)
        print(import_opportunities(session, records))


if __name__ == "__main__":
    main()
