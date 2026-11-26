import io
import sqlite3

from cryptography.fernet import Fernet

from app.services import secure_fields
from scripts.check_decrypt import check_database


def test_check_decrypt_scans_encrypted_columns_read_only_and_redacts_values(tmp_path, monkeypatch):
    database_path = tmp_path / "synthetic.sqlite3"
    active_key = Fernet.generate_key()
    wrong_key = Fernet.generate_key()
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(active_key))

    good_token = Fernet(active_key).encrypt(b"SYNTHETIC-PLAINTEXT-MARKER")
    wrong_key_token = Fernet(wrong_key).encrypt(b"OTHER-PLAINTEXT-MARKER")
    malformed_token = b"not-a-fernet-token"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            "CREATE TABLE sample_records (id INTEGER PRIMARY KEY, payload_encrypted BLOB);"
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, is_encrypted INTEGER NOT NULL);"
        )
        connection.executemany(
            "INSERT INTO sample_records(payload_encrypted) VALUES (?)",
            [(good_token,), (wrong_key_token,), (malformed_token,)],
        )
        connection.executemany(
            "INSERT INTO tasks(title, is_encrypted) VALUES (?, ?)",
            [(good_token.decode("ascii"), 1), (wrong_key_token.decode("ascii"), 1), ("auto title", 0)],
        )

    database_bytes_before = database_path.read_bytes()
    output = io.StringIO()
    failures = check_database(database_path, output)
    report = output.getvalue()

    assert failures == 3, report
    assert "sample_records.payload_encrypted: total=3 ok=1 fail=2" in report
    assert "tasks.title: total=2 ok=1 fail=1" in report
    assert "rowid=2 error=InvalidToken format=fernet-format" in report
    assert "rowid=3 error=InvalidToken format=NOT-fernet-format" in report
    for token in (good_token, wrong_key_token, malformed_token):
        assert token.decode("ascii") not in report
    for plaintext in ("SYNTHETIC-PLAINTEXT-MARKER", "OTHER-PLAINTEXT-MARKER", "auto title"):
        assert plaintext not in report
    assert database_path.read_bytes() == database_bytes_before


def test_check_decrypt_handles_empty_encrypted_columns(tmp_path, monkeypatch):
    database_path = tmp_path / "empty.sqlite3"
    monkeypatch.setattr(secure_fields, "_fernet", lambda: Fernet(Fernet.generate_key()))
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE empty_records (id INTEGER PRIMARY KEY, value_encrypted BLOB)")

    output = io.StringIO()
    assert check_database(database_path, output) == 0
    assert output.getvalue() == "empty_records.value_encrypted: total=0 ok=0 fail=0\n"