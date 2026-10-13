import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.storage import PROJECT_ROOT


VALID_VERDICTS = {"PASS", "FAIL", "ERROR", "INCONCLUSIVE"}


def determine_exit_code(verdicts):
    if not verdicts:
        return 2

    if any(verdict not in VALID_VERDICTS for verdict in verdicts):
        return 2

    # Uncertain evaluations must never be reported as successful.
    if any(
        verdict in {"ERROR", "INCONCLUSIVE"}
        for verdict in verdicts
    ):
        return 2

    if "FAIL" in verdicts:
        return 1

    return 0


def validate_report(report, expected_mode):
    if report["status"] != "COMPLETE":
        raise ValueError("Report is incomplete")

    if report["server_mode"] != expected_mode:
        raise ValueError("Unexpected server mode")

    results = report["results"]

    if report["evaluated_cases"] != 24 or len(results) != 24:
        raise ValueError("Expected 24 evaluated cases")

    if len({result["case_id"] for result in results}) != 24:
        raise ValueError("Case IDs are not unique")

    operations = Counter(result["operation"] for result in results)
    if operations != {"read": 8, "update": 8, "delete": 8}:
        raise ValueError("Unexpected operation counts")

    expectations = Counter(
        result["expected_permission"] for result in results
    )
    if expectations != {"ALLOW": 12, "DENY": 12}:
        raise ValueError("Unexpected permission counts")

    counts = dict(Counter(result["verdict"] for result in results))
    if report["verdict_counts"] != counts:
        raise ValueError("Verdict summary does not match results")

    if report["all_documents_restored"] is not True:
        raise ValueError("Document restoration not confirmed")

    return [result["verdict"] for result in results]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output).resolve()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.matrix_cases",
            "--mode",
            args.mode,
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )

    if completed.returncode != 0:
        print(
            "Regression result: EVALUATION ERROR "
            "(runner did not complete)"
        )
        raise SystemExit(2)

    try:
        report = json.loads(output.read_text())
        verdicts = validate_report(report, args.mode)
        exit_code = determine_exit_code(verdicts)

    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            "Regression result: EVALUATION ERROR",
            type(error).__name__,
        )
        raise SystemExit(2)

    labels = {
        0: "PASS",
        1: "POLICY FAILURE",
        2: "ERROR OR INCONCLUSIVE",
    }

    print("Regression result:", labels[exit_code])
    print("Regression exit code:", exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
