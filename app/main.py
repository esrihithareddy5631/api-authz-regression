import secrets
import time

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from app.storage import database, verify_password

app = FastAPI(title="Authorization Regression Lab")
bearer = HTTPBearer(auto_error=False)

# Local lab sessions; cleared whenever the server restarts.
sessions = {}


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


def authentication_error():
    return HTTPException(
        status_code=401,
        detail="Invalid or missing authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    if credentials is None:
        raise authentication_error()

    session = sessions.get(credentials.credentials)

    if session is None or session["expires_at"] <= time.time():
        raise authentication_error()

    with database() as connection:
        user = connection.execute(
            """
            SELECT id, username, role, tenant_id
            FROM users WHERE id = ?
            """,
            (session["user_id"],),
        ).fetchone()

    if user is None:
        raise authentication_error()

    return dict(user)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/login")
def login(body: LoginRequest):
    with database() as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()

    if user is None or not verify_password(
        body.password, user["password_hash"]
    ):
        raise authentication_error()

    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "user_id": user["id"],
        "expires_at": time.time() + 3600,
    }

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
    }


@app.get("/me")
def me(user=Depends(current_user)):
    return user


import os


LAB_MODE = os.environ.get("LAB_MODE", "fixed")
VALID_MODES = {
    "fixed",
    "read_owner_bypass",
    "update_owner_bypass",
    "delete_owner_bypass",
    "admin_tenant_bypass",
}

if LAB_MODE not in VALID_MODES:
    raise RuntimeError(f"Unknown LAB_MODE: {LAB_MODE}")

print(f"Local authorization lab mode: {LAB_MODE}")


@app.middleware("http")
async def identify_lab_mode(request, call_next):
    response = await call_next(request)
    response.headers["X-Lab-Mode"] = LAB_MODE
    return response


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str


def authorize_document(user, document, operation):
    is_admin = user["role"] == "admin"

    # Deliberate defect: administrators bypass tenant isolation.
    if LAB_MODE == "admin_tenant_bypass" and is_admin:
        return

    if user["tenant_id"] != document["tenant_id"]:
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    # Each mode bypasses ownership for only one operation.
    if LAB_MODE == f"{operation}_owner_bypass":
        return

    is_owner = user["id"] == document["owner_id"]
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )


def find_document(connection, document_id):
    document = connection.execute(
        """
        SELECT id, owner_id, tenant_id, content
        FROM documents
        WHERE id = ?
        """,
        (document_id,),
    ).fetchone()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return dict(document)


@app.get("/documents/{document_id}")
def read_document(document_id: str, user=Depends(current_user)):
    with database() as connection:
        document = find_document(connection, document_id)
        authorize_document(user, document, "read")
        return document


@app.patch("/documents/{document_id}")
def update_document(
    document_id: str,
    body: DocumentUpdate,
    user=Depends(current_user),
):
    with database() as connection:
        document = find_document(connection, document_id)
        authorize_document(user, document, "update")

        connection.execute(
            "UPDATE documents SET content = ? WHERE id = ?",
            (body.content, document_id),
        )

    return {"id": document_id, "updated": True}


@app.delete("/documents/{document_id}")
def delete_document(document_id: str, user=Depends(current_user)):
    with database() as connection:
        document = find_document(connection, document_id)
        authorize_document(user, document, "delete")

        connection.execute(
            "DELETE FROM documents WHERE id = ?",
            (document_id,),
        )

    return {"id": document_id, "deleted": True}
