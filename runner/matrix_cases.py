import argparse
import csv
import json
import uuid
from collections import Counter
from pathlib import Path
from time import perf_counter

import httpx

from app.storage import PROJECT_ROOT
from runner.day8_probes import restore, snapshot
from runner.read_cases import authenticate


def load_inputs():
    with (
        PROJECT_ROOT / "docs" / "permission-matrix.csv"
    ).open(newline="") as file:
        cases = list(csv.DictReader(file))

    fixtures = json.loads(
        (
            PROJECT_ROOT / "evidence" / "lab-fixtures.json"
        ).read_text()
    )

    if len(cases) != 24:
        raise ValueError("Expected 24 matrix cases")

    if len({case["case_id"] for case in cases}) != 24:
        raise ValueError("Duplicate case IDs")

    if Counter(case["operation"] for case in cases) != {
        "read": 8,
        "update": 8,
        "delete": 8,
    }:
        raise ValueError("Expected eight cases per operation")

    for case in cases:
        if case["expected"] not in {"ALLOW", "DENY"}:
            raise ValueError("Invalid expected permission")

        if case["target"] not in fixtures["documents"]:
            raise ValueError("Unknown document alias")

        actor = case["actor"]
        if actor != "anonymous" and actor not in fixtures["users"]:
            raise ValueError("Unknown actor")

    return cases, fixtures


def evaluate(expected, operation, status, body, before, after, marker):
    changed = before != after
    private_marker_present = (
        before["content"] in json.dumps(body)
    )

    if expected == "DENY":
        if changed or (
            operation == "read" and private_marker_present
        ):
            return "FAIL", "Prohibited effect observed"

        if status in (401, 403):
            return "PASS", "Explicit denial; no checked prohibited effect"

        return "INCONCLUSIVE", "No explicit denial or confirmed violation"

    # An allowed read must not modify the document.
    if operation == "read":
        success = (
            status == 200
            and isinstance(body, dict)
            and body == before
            and not changed
        )

    elif operation == "update":
        success = (
            status == 200
            and after is not None
            and after["content"] == marker
            and all(
                after[key] == before[key]
                for key in ("id", "owner_id", "tenant_id")
            )
        )

    else:
        success = status == 200 and after is None

    if success:
        return "PASS", "Expected authorized effect verified"

    if status in (401, 403):
        return "FAIL", "Expected legitimate access denied"

    return "INCONCLUSIVE", "Expected authorized effect not established"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cases, fixtures = load_inputs()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    initial_documents = {}
    for alias, fixture in fixtures["documents"].items():
        actual = snapshot(fixture["id"])

        expected = {
            "id": fixture["id"],
            "owner_id": fixtures["users"][fixture["owner"]]["id"],
            "tenant_id": fixture["tenant"],
            "content": fixture["content"],
        }

        if actual != expected:
            raise RuntimeError(
                f"Fixture/database mismatch for {alias}; stop"
            )

        initial_documents[alias] = actual

    results = []
    run_started = perf_counter()

    # Preserve previous reports and mark interrupted runs incomplete.
    with output.open("x") as report:
        report.write('{"status": "INCOMPLETE"}\n')
        report.flush()

        with httpx.Client(
            base_url="http://127.0.0.1:8000",
            timeout=5,
            trust_env=False,
        ) as client:
            health = client.get("/health")
            health.raise_for_status()
            observed_mode = health.headers.get("X-Lab-Mode")

            if observed_mode != args.mode:
                raise RuntimeError(
                    f"Server mode {observed_mode} != {args.mode}"
                )

            headers_by_actor = {"anonymous": {}}
            actors = sorted(
                {case["actor"] for case in cases} - {"anonymous"}
            )

            for actor in actors:
                headers_by_actor[actor] = authenticate(
                    client,
                    actor,
                    fixtures["users"][actor],
                )

            for case in cases:
                fixture = fixtures["documents"][case["target"]]
                document_id = fixture["id"]
                before = snapshot(document_id)

                if before != initial_documents[case["target"]]:
                    raise RuntimeError(
                        "Case isolation failed; stop evaluation"
                    )

                marker = f"MATRIX-{uuid.uuid4()}"
                status = None
                body = None
                error = None
                after = None
                started = perf_counter()

                try:
                    url = f"/documents/{document_id}"
                    headers = headers_by_actor[case["actor"]]

                    try:
                        if case["operation"] == "read":
                            response = client.get(url, headers=headers)
                        elif case["operation"] == "update":
                            response = client.patch(
                                url,
                                headers=headers,
                                json={"content": marker},
                            )
                        else:
                            response = client.delete(
                                url,
                                headers=headers,
                            )

                        status = response.status_code

                        try:
                            body = response.json()
                        except ValueError:
                            body = response.text

                    except httpx.RequestError as exception:
                        error = type(exception).__name__

                    after = snapshot(document_id)

                    if error is not None:
                        verdict = "ERROR"
                        reason = "Request outcome uncertain"
                    else:
                        verdict, reason = evaluate(
                            case["expected"],
                            case["operation"],
                            status,
                            body,
                            before,
                            after,
                            marker,
                        )

                    elapsed_ms = round(
                        (perf_counter() - started) * 1000,
                        3,
                    )

                finally:
                    # Capture evidence before restoring laboratory state.
                    restore(before)

                result = {
                    "case_id": case["case_id"],
                    "actor": case["actor"],
                    "target_alias": case["target"],
                    "operation": case["operation"],
                    "expected_permission": case["expected"],
                    "status_code": status,
                    "response_body": body,
                    "request_error": error,
                    "before": before,
                    "after": after,
                    "requested_marker": marker,
                    "state_changed": before != after,
                    "elapsed_ms": elapsed_ms,
                    "verdict": verdict,
                    "reason": reason,
                }
                results.append(result)

                print(
                    case["case_id"],
                    verdict,
                    f"status={status}",
                    f"state_changed={result['state_changed']}",
                )

        for alias, original in initial_documents.items():
            assert snapshot(original["id"]) == original, alias

        summary = {
            "status": "COMPLETE",
            "fixture_run_id": fixtures["run_id"],
            "server_mode": observed_mode,
            "evaluated_cases": len(results),
            "operation_counts": dict(
                Counter(r["operation"] for r in results)
            ),
            "expectation_counts": dict(
                Counter(r["expected_permission"] for r in results)
            ),
            "verdict_counts": dict(
                Counter(r["verdict"] for r in results)
            ),
            "runtime_seconds": round(
                perf_counter() - run_started,
                3,
            ),
            "all_documents_restored": True,
            "results": results,
        }

        report.seek(0)
        json.dump(summary, report, indent=2)
        report.write("\n")
        report.truncate()

    print("Verdict counts:", summary["verdict_counts"])
    print("Cases evaluated:", summary["evaluated_cases"])
    print("All documents restored: PASS")
    print("Runtime seconds:", summary["runtime_seconds"])
    print("Report:", output)


if __name__ == "__main__":
    main()
