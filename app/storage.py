import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "evidence" / "lab.db"
FIXTURES_PATH = PROJECT_ROOT / "evidence" / "lab-fixtures.json"


@contextmanager
def database():
    if not DB_PATH.exists():
        raise RuntimeError("Database missing. Run python -m app.seed first.")

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        600_000,
    ).hex()
    return f"{salt}${digest}"


def verify_password(password, stored_hash):
    salt, expected = stored_hash.split("$")
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        600_000,
    ).hex()
    return hmac.compare_digest(actual, expected)
