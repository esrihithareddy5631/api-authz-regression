import json
import uuid
from pathlib import Path

import httpx

from app.storage import database
from runner.read_cases import authenticate


def snapshot(document_id):
    with database() as connection:
        row = connection.execute(
            """
            SELECT id, owner_id, tenant_id, content
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError("Ground-truth document missing")

    return dict(row)


def main():
    fixtures = json.loads(
        Path("evidence/lab-fixtures.json").read_text()
    )
    document_id = fixtures["documents"]["alice_doc"]["id"]
    original = snapshot(document_id)
    results = []

    try:
        with httpx.Client(
            base_url="http://127.0.0.1:8000",
            timeout=5,
            trust_env=False,
        ) as client:
            for case_id, actor, expected in (
                ("U01", "alice", "ALLOW"),
                ("U02", "bob", "DENY"),
            ):
                headers = authenticate(
                    client,
                    actor,
                    fixtures["users"][actor],
                )
                before = snapshot(document_id)
                marker = f"UPDATE-{actor}-{uuid.uuid4()}"

                response = client.patch(
                    f"/documents/{document_id}",
                    headers=headers,
                    json={"content": marker},
                )

                after = snapshot(document_id)
                changed = before != after
                requested_content_written = after["content"] == marker
                metadata_unchanged = all(
                    before[key] == after[key]
                    for key in ("id", "owner_id", "tenant_id")
                )

                if expected == "ALLOW":
                    passed = (
                        response.status_code == 200
                        and requested_content_written
                        and metadata_unchanged
                    )
                else:
                    passed = (
                        response.status_code in (401, 403)
                        and not changed
                    )

                result = {
                    "case_id": case_id,
                    "actor": actor,
                    "expected_permission": expected,
                    "status_code": response.status_code,
                    "state_changed": changed,
                    "requested_content_written": requested_content_written,
                    "metadata_unchanged": metadata_unchanged,
                    "before": before,
                    "after": after,
                    "verdict": "PASS" if passed else "FAIL",
                }
                results.append(result)

                print(
                    case_id,
                    result["verdict"],
                    f"status={response.status_code}",
                    f"state_changed={changed}",
                    f"requested_content_written={requested_content_written}",
                )

    finally:
        # Local laboratory cleanup, outside the API being evaluated.
        # Evidence snapshots are captured before this restoration.
        with database() as connection:
            connection.execute(
                "UPDATE documents SET content = ? WHERE id = ?",
                (original["content"], document_id),
            )

        assert snapshot(document_id) == original
        print("Original document state restored: PASS")

    Path("reports/day7-update-checks.json").write_text(
        json.dumps(
            {"evaluated_cases": len(results), "results": results},
            indent=2,
        ) + "\n"
    )

    if any(result["verdict"] != "PASS" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
