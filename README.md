# API Authorization Regression Testing

A local training project that tests expected document permissions
across users, roles, and tenants.

## Scope

The API contains two tenants, six users, and two private documents.
The permission matrix defines 24 read, update, and delete cases.

The runner checks returned content and document database state.
It restores document state after each evaluated case.

This application and its deliberately vulnerable modes are intended
for local, authorized testing.

## Requirements

Validated environment: Ubuntu 24.04 and Python 3.12.3.
Python virtual-environment support and internet access are needed
to install the dependencies.

## Setup

Open a terminal in the project directory.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip check
mkdir -p evidence reports
python -m app.seed
```

Seeding creates synthetic users, documents, and a fixture mapping.
The training password is defined in app/seed.py.

Do not seed or reset while the application is running.

To deliberately recreate existing synthetic fixtures, stop the
server first, then use:

```bash
python -m app.seed --reset
```

## Fixed configuration

In Terminal 1, activate the environment and start:

```bash
source .venv/bin/activate
LAB_MODE=fixed python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

In Terminal 2, open the same project directory and run:

```bash
source .venv/bin/activate
python -m runner.regression \
  --mode fixed \
  --output reports/fixed-check.json
echo "Exit code: $?"
```

Expected: 24 PASS and exit code 0.

## Demonstrate a seeded defect

Stop the server with Ctrl+C. In Terminal 1:

```bash
LAB_MODE=read_owner_bypass python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

In Terminal 2:

```bash
python -m runner.regression \
  --mode read_owner_bypass \
  --output reports/read-defect-check.json
echo "Exit code: $?"
```

Expected: R02 FAIL, 23 PASS, and exit code 1.

Other selectable defect modes:
- update_owner_bypass
- delete_owner_bypass
- admin_tenant_bypass

Restarting the server clears authentication sessions.
The runner obtains fresh sessions automatically.

## Exit codes

- 0: all evaluated cases passed.
- 1: completed evaluation contains policy failures.
- 2: evaluation failed, was incomplete, or contains unresolved cases.

Read the report as well as the exit code.

## Reports and case isolation

Reports contain synthetic private content and before/after state.
Existing output files are not overwritten: use a fresh filename.

Run one evaluator at a time. Do not reseed, edit the database,
or run another writer while evaluation is in progress.

An interrupted run may leave an INCOMPLETE report.
Inspect logs and database state before restarting an experiment.

## Evidence and limitations

The completed five-round local benchmark executed 600 cases
across 25 fresh fixture sets and four seeded defect implementations.

Measured DENY-case outcomes:
45 true positives, 255 true negatives, zero false positives,
zero false negatives, and no unresolved cases.

All 300 ALLOW executions passed.

These repeated synthetic cases do not establish production accuracy.
The runner requires privileged SQLite access and checks document-row
state. It can miss partial or transformed disclosures and side effects
outside the checked records.

A four-observation status-only fallback agreed with the verifier.
Autorize setup was attempted but remained incomplete because Jython
configuration was pending. No established-tool comparison was completed.

No research novelty or publication claim is made.
