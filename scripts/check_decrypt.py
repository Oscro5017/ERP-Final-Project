"""Read-only audit of Fernet-encrypted values in a SQLite database.

Usage: python -m scripts.check_decrypt path/to/erp.db
Only counts, row IDs, error types, and token-format labels are printed.
"""

import argparse
import base64
import binascii
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TextIO

from cryptography.fernet import InvalidToken

from app.services.secure_fields import decrypt_text

MAX_FAILURE_ROWS_PER_COLUMN = 10


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _is_fernet_format(token: object) -> bool:
    if isinstance(token, str):
        try:
            token = token.encode("ascii")
        except UnicodeError:
            return False
    if not isinstance(token, bytes):
        return False
    try:
        raw = base64.urlsafe_b64decode(token + b"=" * (-len(token) % 4))
    except (binascii.Error, ValueError):
        return False
    return len(raw) >= 73 and raw[0] == 0x80 and (len(raw) - 57) % 16 == 0


def _audit_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    output: TextIO,
    where: str | None = None,
) -> int:
    table_sql = _quoted_identifier(table)
    column_sql = _quoted_identifier(column)
    where_sql = f" WHERE {where}" if where else ""
    rows = connection.execute(
        f"SELECT rowid, {column_sql} FROM {table_sql}{where_sql} ORDER BY rowid"
    )

    total = ok = failed = 0
    for row_id, token in rows:
        if token is None:
            continue
        total += 1
        try:
            decrypt_text(token)
            ok += 1
        except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
            failed += 1
            if failed <= MAX_FAILURE_ROWS_PER_COLUMN:
                token_format = "fernet-format" if _is_fernet_format(token) else "NOT-fernet-format"
                print(
                    f"  rowid={row_id} error={type(exc).__name__} format={token_format}",
                    file=output,
                )

    print(f"{table}.{column}: total={total} ok={ok} fail={failed}", file=output)
    return failed


def check_database(database_path: str | Path, output: TextIO) -> int:
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database file not found: {path}")

    uri = f"{path.as_uri()}?mode=ro"
    failures = 0
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({_quoted_identifier(table)})")
            }
            for column in sorted(
                column for column in columns
                if column.endswith("_encrypted") and column != "is_encrypted"
            ):
                failures += _audit_column(connection, table, column, output)

            if table == "tasks" and {"title", "is_encrypted"}.issubset(columns):
                failures += _audit_column(connection, table, "title", output, '"is_encrypted" = 1')

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Fernet ciphertexts in a SQLite file opened read-only.")
    parser.add_argument("database", help="SQLite database path; the database is opened read-only")
    args = parser.parse_args()
    try:
        failures = check_database(args.database, output=__import__("sys").stdout)
    except (OSError, sqlite3.Error) as exc:
        parser.error(f"Could not inspect database: {type(exc).__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
