# Day 11: scoped read-authorization comparison

## Environment
Burp version:
Autorize version:
Jython version:
Setup time:
Comparison completed: YES / NO

## Scope
Local synthetic API only.
Configurations: fixed and read_owner_bypass.
Compared prohibited cases: Bob and anonymous reads.
Four prohibited-access observations total.
Alice read used as a legitimate-access control.

## Observations
For each configuration and identity, record:
- HTTP status
- Private content present or absent
- Autorize default label
- Autorize configured label, if configuration was changed
- Our runner verdict
- Manual inspection result
- Any uncertainty

## Detector configuration
Record exact settings and any changes.
If none were changed, state that explicitly.

## Limitations
No independent training application evaluated.
No update or delete comparison.
Our runner has privileged SQLite access.
Tool configuration and session validity may affect results.
This is not evidence of production effectiveness or novelty.

