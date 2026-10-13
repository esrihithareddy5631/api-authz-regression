import argparse
import csv
import json
from pathlib import Path
from time import perf_counter

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "http://127.0.0.1:8000"
LAB_PASSWORD = "LabOnly-2026!"


def load_inputs():
    matrix_path = PROJECT_ROOT / "docs" / "permission-matrix.csv"
    fixtures_path = PROJECT_ROOT / "evidence" / "lab-fixtures.json"

    with matrix_path.open(newline="") as file:
        cases = [
            row
            for row in csv.DictReader(file)
            if row["operation"] == "read"
        ]

    fixtures = json.loads(fixtures_path.read_text())

    if len(cases) != 8:
        raise ValueError("Expected exactly eight read cases")

    if len({case["case_id"] for case in cases}) != 8:
        raise ValueError("Read case IDs must be unique")

    for case in cases:
        if case["expected"] not in {"ALLOW", "DENY"}:
            raise ValueError("Invalid expected permission")

        if case["target"] not in fixtures["documents"]:
            raise ValueError("Unknown document alias")

        actor = case["actor"]
        if actor != "anonymous" and actor not in fixtures["users"]:
            raise ValueError("Unknown actor")

    return cases, fixtures


def authenticate(client, actor, expected_user):
    response = client.post(
        "/login",
        json={"username": actor, "password": LAB_PASSWORD},
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/me", headers=headers)
    response.raise_for_status()
    actual = response.json()

    expected_identity = (
        actor,
        expected_user["id"],
        expected_user["role"],
        expected_user["tenant"],
    )
    actual_identity = (
        actual["username"],
        actual["id"],
        actual["role"],
        actual["tenant_id"],
    )

    if actual_identity != expected_identity:
        raise RuntimeError(
            f"Identity mismatch for {actor}; check current fixtures"
        )

    return headers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_path = Path(args.output)
    cases, fixtures = load_inputs()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    request_errors = 0

    with httpx.Client(
        base_url=BASE_URL,
        timeout=5,
        trust_env=False,
    ) as client:
        client.get("/health").raise_for_status()

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

        # "x" prevents accidentally overwriting an existing report.
        with output_path.open("x") as report:
            for case in cases:
                document = fixtures["documents"][case["target"]]

                observation = {
                    "fixture_run_id": fixtures["run_id"],
                    "case_id": case["case_id"],
                    "actor": case["actor"],
                    "target_alias": case["target"],
                    "document_id": document["id"],
                    "operation": "read",
                    "expected_permission": case["expected"],
                    "status_code": None,
                    "response_body": None,
                    "request_error": None,
                }

                started = perf_counter()

                try:
                    response = client.get(
                        f"/documents/{document['id']}",
                        headers=headers_by_actor[case["actor"]],
                    )
                    observation["status_code"] = response.status_code

                    try:
                        observation["response_body"] = response.json()
                    except ValueError:
                        observation["response_body"] = response.text

                except httpx.RequestError as error:
                    observation["request_error"] = type(error).__name__
                    request_errors += 1

                observation["elapsed_ms"] = round(
                    (perf_counter() - started) * 1000,
                    3,
                )

                report.write(json.dumps(observation) + "\n")

                print(
                    case["case_id"],
                    case["actor"],
                    case["target"],
                    f"expected={case['expected']}",
                    f"status={observation['status_code']}",
                    f"error={observation['request_error']}",
                )

    print(f"Cases recorded: {len(cases)}")
    print(f"Request errors: {request_errors}")
    print(f"Report: {output_path}")

    if request_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
