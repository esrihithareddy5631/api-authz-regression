import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from app.storage import PROJECT_ROOT


MODES = (
    "fixed",
    "read_owner_bypass",
    "update_owner_bypass",
    "delete_owner_bypass",
    "admin_tenant_bypass",
)


def port_busy():
    with socket.socket() as connection:
        return connection.connect_ex(("127.0.0.1", 8000)) == 0


def wait_for_server(process, mode):
    deadline = time.monotonic() + 15

    with httpx.Client(timeout=1, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Server exited during startup")

            try:
                response = client.get(
                    "http://127.0.0.1:8000/health"
                )
                if (
                    response.status_code == 200
                    and response.headers.get("X-Lab-Mode") == mode
                ):
                    return
            except httpx.RequestError:
                pass

            time.sleep(0.2)

    raise RuntimeError("Server startup timed out")


def stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    if port_busy():
        raise RuntimeError("Port 8000 remains busy after shutdown")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    if args.rounds < 1:
        raise ValueError("Rounds must be positive")

    if port_busy():
        raise RuntimeError("Stop the existing server first")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "status": "INCOMPLETE",
        "requested_rounds": args.rounds,
        "completed_evaluations": [],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    for round_number in range(1, args.rounds + 1):
        for mode in MODES:
            label = f"round{round_number}-{mode}"
            seed_log = output_dir / f"{label}-seed.log"

            # Reset only the synthetic laboratory database.
            # No server is running while fixtures are recreated.
            with seed_log.open("w") as log:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "app.seed",
                        "--reset",
                    ],
                    cwd=PROJECT_ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )

            fixtures = json.loads(
                (
                    PROJECT_ROOT / "evidence" / "lab-fixtures.json"
                ).read_text()
            )

            server_log = output_dir / f"{label}-server.log"
            runner_log = output_dir / f"{label}-runner.log"
            report_path = output_dir / f"{label}.json"

            environment = os.environ.copy()
            environment["LAB_MODE"] = mode

            with server_log.open("w") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                    ],
                    cwd=PROJECT_ROOT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )

                try:
                    wait_for_server(process, mode)

                    with runner_log.open("w") as runner_output:
                        completed = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "runner.regression",
                                "--mode",
                                mode,
                                "--output",
                                str(report_path),
                            ],
                            cwd=PROJECT_ROOT,
                            stdout=runner_output,
                            stderr=subprocess.STDOUT,
                            check=False,
                        )

                    if completed.returncode not in (0, 1):
                        raise RuntimeError(
                            f"{label}: evaluation error; inspect logs"
                        )

                    report = json.loads(report_path.read_text())
                    if report["status"] != "COMPLETE":
                        raise RuntimeError("Incomplete matrix report")

                    entry = {
                        "round": round_number,
                        "mode": mode,
                        "fixture_run_id": fixtures["run_id"],
                        "document_ids": {
                            alias: document["id"]
                            for alias, document
                            in fixtures["documents"].items()
                        },
                        "report_file": report_path.name,
                        "exit_code": completed.returncode,
                    }
                    manifest["completed_evaluations"].append(entry)

                    manifest_path.write_text(
                        json.dumps(manifest, indent=2) + "\n"
                    )

                    print(
                        label,
                        report["verdict_counts"],
                        f"exit={completed.returncode}",
                        flush=True,
                    )

                finally:
                    stop_server(process)

    manifest["status"] = "COMPLETE"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print("Repeat experiment: COMPLETE")
    print("Evaluations:", len(manifest["completed_evaluations"]))
    print("Output directory:", output_dir)


if __name__ == "__main__":
    main()
