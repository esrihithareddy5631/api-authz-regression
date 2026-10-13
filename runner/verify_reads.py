import json
from collections import Counter
from pathlib import Path

from app.storage import database


def main():
    evidence = Path("evidence")
    fixtures = json.loads(
        (evidence / "lab-fixtures.json").read_text()
    )
    observations = [
        json.loads(line)
        for line in Path(
            "reports/day6-read-run2.jsonl"
        ).read_text().splitlines()
    ]

    assert len(observations) == 8
    assert len({r["case_id"] for r in observations}) == 8

    results = []

    with database() as connection:
        for record in observations:
            assert record["fixture_run_id"] == fixtures["run_id"]
            fixture = fixtures["documents"][record["target_alias"]]
            assert record["document_id"] == fixture["id"]

            row = connection.execute(
                """
                SELECT id, owner_id, tenant_id, content
                FROM documents
                WHERE id = ?
                """,
                (record["document_id"],),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "Ground-truth document missing; stop verification"
                )

            actual = dict(row)

            # Historical responses cannot safely be compared against
            # a document that has changed since the fixture was created.
            assert actual["content"] == fixture["content"], (
                "Document content changed; collect a fresh read report "
                "with matching ground truth before evaluating it"
            )
            assert actual["owner_id"] == (
                fixtures["users"][fixture["owner"]]["id"]
            )
            assert actual["tenant_id"] == fixture["tenant"]

            body = record["response_body"]
            body_text = json.dumps(body)
            marker_present = actual["content"] in body_text
            exact_document = isinstance(body, dict) and body == actual
            status = record["status_code"]

            if record["request_error"] is not None:
                verdict = "ERROR"
                reason = "Request did not complete"

            elif record["expected_permission"] == "DENY":
                if marker_present:
                    verdict = "FAIL"
                    reason = "Protected content marker exposed"
                elif status in (401, 403):
                    verdict = "PASS"
                    reason = "Explicit denial without content marker"
                else:
                    verdict = "INCONCLUSIVE"
                    reason = "Neither exposure nor explicit denial established"

            elif status == 200 and exact_document:
                verdict = "PASS"
                reason = "Correct authorized document returned"

            elif status in (401, 403):
                verdict = "FAIL"
                reason = "Expected legitimate access was denied"

            else:
                verdict = "INCONCLUSIVE"
                reason = "Expected document access not established"

            result = {
                "case_id": record["case_id"],
                "actor": record["actor"],
                "expected_permission": record["expected_permission"],
                "status_code": status,
                "private_marker_present": marker_present,
                "verdict": verdict,
                "reason": reason,
            }
            results.append(result)
            print(
                result["case_id"],
                result["verdict"],
                result["reason"],
            )

    summary = {
        "evaluated_cases": len(results),
        "verdict_counts": dict(
            Counter(result["verdict"] for result in results)
        ),
        "results": results,
        "limitations": [
            "Exact content marker check can miss partial disclosures",
            "Evaluation is restricted to this local synthetic application",
        ],
    }

    Path("reports/day7-read-verdicts.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print("Counts:", summary["verdict_counts"])


if __name__ == "__main__":
    main()
