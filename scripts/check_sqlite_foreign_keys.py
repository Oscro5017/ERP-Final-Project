"""Read-only foreign-key audit using a temporary SQLite backup copy.

Usage: python -m scripts.check_sqlite_foreign_keys path/to/erp.db
Only table names and violation counts are printed; no row values are exposed.
"""

import argparse
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path


def foreign_key_violations(
    database_path: str | Path,
    temporary_parent: str | Path | None = None,
) -> dict[str, int]:
    source_path = Path(database_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Database file not found: {source_path}")

    with tempfile.TemporaryDirectory(prefix="erp-fk-audit-", dir=temporary_parent) as temporary_directory:
        copy_path = Path(temporary_directory) / "audit-copy.sqlite3"
        source_uri = f"{source_path.as_uri()}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            with closing(sqlite3.connect(copy_path)) as copy:
                source.backup(copy)
                copy.commit()

        with closing(sqlite3.connect(f"file:{copy_path.as_posix()}?mode=ro", uri=True)) as copy:
            violations = copy.execute("PRAGMA foreign_key_check").fetchall()

    counts = Counter(str(row[0]) for row in violations)
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check foreign-key violations on a temporary read-only copy.")
    parser.add_argument("database", help="SQLite database path; source is opened read-only")
    args = parser.parse_args()
    violations = foreign_key_violations(args.database)
    if not violations:
        print("Foreign-key check passed: no violations found in the temporary copy.")
        return 0
    print("Foreign-key violations found (table: count); no rows were changed:")
    for table, count in violations.items():
        print(f"  {table}: {count}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
