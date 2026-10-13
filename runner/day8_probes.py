import argparse
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

    return None if row is None else dict(row)


def restore(document):
    with database() as connection:
        connection.execute(
            """
            INSERT INTO documents (id, owner_id, tenant_id, content)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner_id = excluded.owner_id,
                tenant_id = excluded.tenant_id,
                content = excluded.content
            """,
            (
                document["id"],
                document["owner_id"],
                document["tenant_id"],
                document["content"],
            ),
        )

    assert snapshot(document["id"]) == document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()

    fixtures = json.loads(
        Path("evidence/lab-fixtures.json").read_text()
    )

    cases = [
        ("update_peer", "bob", "alice_doc", "update", "DENY"),
        ("delete_peer", "bob", "alice_doc", "delete", "DENY"),
        ("admin_cross_read", "admin_a", "carol_doc", "read", "DENY"),
        ("owner_delete", "alice", "alice_doc", "delete", "ALLOW"),
    ]

    output = Path(f"reports/day8-{args.mode}.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    # Reserve the output name without overwriting prior evidence.
    with output.open("x") as file:
        file.write('{"status": "INCOMPLETE"}\n')

    results = []

    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=5,
        trust_env=False,
    ) as client:
        health = client.get("/health")
        health.raise_for_status()
        observed_mode = health.headers.get("X-Lab-Mode")
        assert observed_mode == args.mode, (
            f"Server mode is {observed_mode}, not {args.mode}"
        )

        for case_id, actor, alias, operation, expected in cases:
            document_id = fixtures["documents"][alias]["id"]
            before = snapshot(document_id)
            assert before is not None

            headers = authenticate(
                client,
                actor,
                fixtures["users"][actor],
            )
            marker = f"DAY8-{uuid.uuid4()}"

            try:
                url = f"/documents/{document_id}"

                if operation == "read":
                    response = client.get(url, headers=headers)
                elif operation == "update":
                    response = client.patch(
                        url,
                        headers=headers,
                        json={"content": marker},
                    )
                else:
                    response = client.delete(url, headers=headers)

                after = snapshot(document_id)

                if operation == "read":
                    effect = before["content"] in response.text
                elif operation == "update":
                    effect = (
                        after is not None
                        and after["content"] == marker
                    )
                else:
                    effect = after is None

                changed = before != after

                if expected == "DENY":
                    if effect or changed:
                        verdict = "FAIL"
                    elif response.status_code in (401, 403):
                        verdict = "PASS"
                    else:
                        verdict = "INCONCLUSIVE"
                else:
                    verdict = (
                        "PASS"
                        if effect and response.status_code == 200
                        else "FAIL"
                    )

                result = {
                    "case_id": case_id,
                    "actor": actor,
                    "target_alias": alias,
                    "operation": operation,
                    "expected_permission": expected,
                    "server_mode": observed_mode,
                    "status_code": response.status_code,
                    "protected_effect_observed": effect,
                    "state_changed": changed,
                    "before": before,
                    "after": after,
                    "verdict": verdict,
                }
                results.append(result)

                print(
                    case_id,
                    verdict,
                    f"status={response.status_code}",
                    f"effect={effect}",
                    f"state_changed={changed}",
                )

            finally:
                # Privileged local cleanup after recording the effect.
                restore(before)

    output.write_text(
        json.dumps(
            {
                "status": "COMPLETE",
                "server_mode": observed_mode,
                "evaluated_cases": len(results),
                "results": results,
            },
            indent=2,
        ) + "\n"
    )
    print("All probe documents restored: PASS")
    print("Report:", output)


if __name__ == "__main__":
    main()
