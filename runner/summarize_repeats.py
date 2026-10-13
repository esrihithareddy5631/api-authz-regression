import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median


KNOWN_VIOLATIONS = {
    "fixed": set(),
    "read_owner_bypass": {"R02"},
    "update_owner_bypass": {"U02"},
    "delete_owner_bypass": {"D02"},
    "admin_tenant_bypass": {
        "R06", "R07", "U06", "U07", "D06", "D07"
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    args = parser.parse_args()

    directory = Path(args.input_dir)
    manifest = json.loads(
        (directory / "manifest.json").read_text()
    )
    assert manifest["status"] == "COMPLETE"

    entries = manifest["completed_evaluations"]
    rounds = manifest["requested_rounds"]
    assert len(entries) == rounds * 5

    combinations = {(e["round"], e["mode"]) for e in entries}
    assert len(combinations) == len(entries)

    assert len({e["fixture_run_id"] for e in entries}) == len(entries)

    all_document_ids = [
        document_id
        for entry in entries
        for document_id in entry["document_ids"].values()
    ]
    assert len(set(all_document_ids)) == len(all_document_ids)

    detection = Counter()
    legitimate = Counter()
    runtimes = {mode: [] for mode in KNOWN_VIOLATIONS}
    signatures = {}
    inconsistent_modes = set()
    total_cases = 0

    for entry in entries:
        mode = entry["mode"]
        report = json.loads(
            (directory / entry["report_file"]).read_text()
        )

        assert report["status"] == "COMPLETE"
        assert report["server_mode"] == mode
        assert report["fixture_run_id"] == entry["fixture_run_id"]
        assert report["evaluated_cases"] == 24
        assert len(report["results"]) == 24
        assert report["all_documents_restored"] is True

        results = report["results"]
        total_cases += len(results)
        runtimes[mode].append(report["runtime_seconds"])

        signature = tuple(sorted(
            (
                result["case_id"],
                result["verdict"],
                result["status_code"],
                result["state_changed"],
            )
            for result in results
        ))

        if mode in signatures and signatures[mode] != signature:
            inconsistent_modes.add(mode)
        signatures.setdefault(mode, signature)

        for result in results:
            verdict = result["verdict"]

            if result["expected_permission"] == "ALLOW":
                legitimate[verdict] += 1
                continue

            actual_violation = (
                result["case_id"] in KNOWN_VIOLATIONS[mode]
            )

            if verdict in {"ERROR", "INCONCLUSIVE"}:
                detection[verdict] += 1
            elif verdict == "FAIL":
                detection["TP" if actual_violation else "FP"] += 1
            elif verdict == "PASS":
                detection["FN" if actual_violation else "TN"] += 1
            else:
                raise ValueError("Unknown verdict")

    summary = {
        "fixture_sets": len(entries),
        "matrix_case_executions": total_cases,
        "distinct_seeded_defects": 4,
        "deny_case_detection": {
            key: detection[key]
            for key in ("TP", "FP", "FN", "TN", "ERROR", "INCONCLUSIVE")
        },
        "allow_case_verdicts": dict(legitimate),
        "inconsistent_modes": sorted(inconsistent_modes),
        "matrix_runtime_seconds": {
            mode: {
                "runs": len(values),
                "median": round(median(values), 3),
                "minimum": min(values),
                "maximum": max(values),
            }
            for mode, values in runtimes.items()
        },
    }

    (directory / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
