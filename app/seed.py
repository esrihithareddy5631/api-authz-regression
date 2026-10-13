import argparse
import json
import sqlite3
import uuid

from app.storage import DB_PATH, FIXTURES_PATH, hash_password

LAB_PASSWORD = "LabOnly-2026!"

ACCOUNTS = [
    ("alice", "user", "A"),
    ("bob", "user", "A"),
    ("admin_a", "admin", "A"),
    ("carol", "user", "B"),
    ("dave", "user", "B"),
    ("admin_b", "admin", "B"),
]


def seed(reset=False):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists() and not reset:
        raise SystemExit(
            "Database already exists. Stop the server before using --reset."
        )

    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL REFERENCES users(id),
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                content TEXT NOT NULL
            );
        """)

        fixtures = {
            "run_id": str(uuid.uuid4()),
            "users": {},
            "documents": {},
        }

        with connection:
            if reset:
                connection.execute("DELETE FROM documents")
                connection.execute("DELETE FROM users")
                connection.execute("DELETE FROM tenants")

            connection.executemany(
                "INSERT INTO tenants (id) VALUES (?)",
                [("A",), ("B",)],
            )

            for username, role, tenant in ACCOUNTS:
                user_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO users
                    (id, username, password_hash, role, tenant_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        username,
                        hash_password(LAB_PASSWORD),
                        role,
                        tenant,
                    ),
                )
                fixtures["users"][username] = {
                    "id": user_id,
                    "role": role,
                    "tenant": tenant,
                }

            for alias, owner in [
                ("alice_doc", "alice"),
                ("carol_doc", "carol"),
            ]:
                document_id = str(uuid.uuid4())
                user = fixtures["users"][owner]
                content = f"PRIVATE-{alias}-{uuid.uuid4()}"

                connection.execute(
                    """
                    INSERT INTO documents
                    (id, owner_id, tenant_id, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (document_id, user["id"], user["tenant"], content),
                )

                fixtures["documents"][alias] = {
                    "id": document_id,
                    "owner": owner,
                    "tenant": user["tenant"],
                    "content": content,
                }

        FIXTURES_PATH.write_text(json.dumps(fixtures, indent=2) + "\n")
        print("Seed complete: 2 tenants, 6 users, 2 documents")
        print("Fixture mapping:", FIXTURES_PATH)

    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    arguments = parser.parse_args()
    seed(reset=arguments.reset)
