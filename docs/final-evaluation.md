# Final validation evaluation

## Implemented
- Local FastAPI document API with SQLite.
- Six identities across two tenants.
- Independent CSV permission expectations.
- Read, update, and delete request execution.
- Fresh session acquisition and identity verification.
- Dynamic document-ID resolution.
- Response-content and database-state verification.
- Structured reports and laboratory state restoration.
- Regression exit codes: 0, 1, and 2.
- Four separately selectable seeded defect modes.

## Measured results
Completed dataset: reports/day12-repeat-retry1

25 fresh fixture sets.
600 matrix-case executions.
Four distinct seeded defects.

DENY cases:
45 TP, 255 TN, 0 FP, 0 FN.
No ERROR or INCONCLUSIVE outcomes in the completed dataset.

ALLOW cases:
300 PASS.

No inconsistent configurations across five rounds.

Per-configuration median matrix runtime:
fixed: 3.779 seconds
read_owner_bypass: 3.607 seconds
update_owner_bypass: 3.453 seconds
delete_owner_bypass: 3.397 seconds
admin_tenant_bypass: 3.889 seconds

Runtime excludes seeding and server startup.

## Reproduction
Separate source copy, virtual environment, and database
on the same Ubuntu VM.

Fixed configuration: 24 PASS, exit 0.
Read defect: R02 FAIL, exit 1.

## Comparison
Status-only fallback agreed on four read observations.
No added detection benefit demonstrated on that subset.
Autorize setup remained incomplete; Jython configuration pending.

## Limitations
One self-built synthetic application.
Repeated executions are correlated.
Only four seeded defect implementations.
Privileged SQLite access is required.
Only document-row state is checked.
Partial or transformed disclosure may be missed.
Concurrent or asynchronous effects are not evaluated.
The 24-case matrix does not exhaust all identity/object combinations.
No independent application or completed established-tool comparison.
No production detection accuracy or research novelty established.

## Evidence handling
The earlier interrupted Day 12 attempt is excluded from the
completed benchmark metrics.


Day 14 live demonstration:
- day14-read-recovery1.json: 23 PASS, R02 FAIL, exit 1.
- day14-fixed-recovery1.json: 24 PASS, exit 0.
- Both runs restored document state.
- Earlier reproduction-directory demo attempts were incomplete
  and excluded from successful demonstration results.
