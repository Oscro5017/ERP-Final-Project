import base64
import binascii
import warnings
from dataclasses import dataclass
from decimal import InvalidOperation

from cryptography.fernet import InvalidToken
from sqlalchemy import MetaData, Table, inspect, literal_column, select
from sqlalchemy.engine import Connection

from .secure_fields import decrypt_text

MAX_FAILURE_ROWS_PER_COLUMN = 10


@dataclass(frozen=True)
class EncryptedValueFailure:
    row_id: object
    error_type: str
    token_format: str


@dataclass(frozen=True)
class EncryptedColumnAudit:
    table: str
    column: str
    total: int
    ok: int
    fail: int
    failures: tuple[EncryptedValueFailure, ...]


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


def _row_identifier_columns(table: Table, dialect_name: str):
    primary_key = list(table.primary_key.columns)
    if primary_key:
        return primary_key
    if dialect_name == "sqlite":
        return [literal_column("rowid").label("_audit_rowid")]
    return []


# Activities keep the title encrypted only for manual rows; "tasks" is the table name before the rename.
_TITLE_TABLES = {"activities", "tasks"}


def audit_encrypted_data(connection: Connection) -> list[EncryptedColumnAudit]:
    inspector = inspect(connection)
    results = []
    dialect_name = connection.dialect.name

    for table_name in sorted(inspector.get_table_names()):
        if table_name.startswith("sqlite_"):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        with warnings.catch_warnings():
            # The finance uniqueness index uses an expression SQLAlchemy cannot reflect; the audit does not need it.
            warnings.filterwarnings("ignore", message="Skipped unsupported reflection of expression-based index")
            table = Table(table_name, MetaData(), autoload_with=connection)
        identifiers = _row_identifier_columns(table, dialect_name)
        encrypted_columns = sorted(
            name for name in columns
            if name.endswith("_encrypted") and name != "is_encrypted"
        )
        if table_name in _TITLE_TABLES and {"title", "is_encrypted"}.issubset(columns):
            encrypted_columns.append("title")

        for column_name in encrypted_columns:
            value_column = table.c[column_name]
            statement = select(*identifiers, value_column).select_from(table)
            if table_name in _TITLE_TABLES and column_name == "title":
                statement = statement.where(table.c.is_encrypted.is_(True))
            total = ok = failed = 0
            failures: list[EncryptedValueFailure] = []

            for sequence, row in enumerate(connection.execute(statement), start=1):
                row_values = row[:-1]
                token = row[-1]
                if token is None:
                    continue
                total += 1
                try:
                    decrypt_text(token)
                    ok += 1
                except (InvalidToken, UnicodeError, InvalidOperation, ValueError, TypeError) as exc:
                    failed += 1
                    if len(failures) < MAX_FAILURE_ROWS_PER_COLUMN:
                        if len(row_values) == 1:
                            row_id = row_values[0]
                        elif row_values:
                            row_id = tuple(row_values)
                        else:
                            row_id = sequence
                        failures.append(EncryptedValueFailure(
                            row_id=row_id,
                            error_type=type(exc).__name__,
                            token_format="fernet-format" if _is_fernet_format(token) else "NOT-fernet-format",
                        ))

            results.append(EncryptedColumnAudit(
                table=table_name,
                column=column_name,
                total=total,
                ok=ok,
                fail=failed,
                failures=tuple(failures),
            ))

    return results
