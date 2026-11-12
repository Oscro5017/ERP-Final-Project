"""Read-only audit of Fernet-encrypted values in a SQLite database.

Usage: python -m scripts.check_decrypt path/to/erp.db
Only counts, row IDs, error types, and token-format labels are printed.
"""

import argparse
from pathlib import Path
import sys
from typing import TextIO
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from app.services.encrypted_data_audit import audit_encrypted_data
from app.services.encryption_canary import encryption_canary_status


def check_database(
    database_path: str | Path,
    output: TextIO,
    include_canary_status: bool = False,
) -> int:
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database file not found: {path}")

    # SQLite URI paths must percent-encode URI-reserved characters such as '#'.
    # This matters on Windows where temporary paths may include sandbox markers.
    sqlite_uri_path = quote(path.as_posix(), safe="/:")
    read_only_url = URL.create(
        "sqlite",
        database=f"file:{sqlite_uri_path}",
        query={"mode": "ro", "uri": "true"},
    )
    engine = create_engine(read_only_url)
    failures = 0
    try:
        with engine.connect() as connection:
            canary = encryption_canary_status(connection)
            if include_canary_status:
                print(f"Encryption canary: {canary}", file=output)
                if canary == "ไม่ตรง":
                    failures += 1

            audits = audit_encrypted_data(connection)
            for result in audits:
                print(
                    f"{result.table}.{result.column}: total={result.total} ok={result.ok} fail={result.fail}",
                    file=output,
                )
                failures += result.fail
                for failure in result.failures:
                    print(
                        f"  rowid={failure.row_id} error={failure.error_type} format={failure.token_format}",
                        file=output,
                    )
    finally:
        engine.dispose()

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Fernet ciphertexts in a SQLite file opened read-only.")
    parser.add_argument("database", help="SQLite database path; the database is opened read-only")
    args = parser.parse_args()
    try:
        failures = check_database(
            args.database,
            output=sys.stdout,
            include_canary_status=True,
        )
    except (OSError, SQLAlchemyError) as exc:
        parser.error(f"Could not inspect database: {type(exc).__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
