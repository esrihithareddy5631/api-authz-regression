import json
from pathlib import Path

from app.storage import database

evidence = Path("evidence")
fixtures = json.loads(
    (evidence / "lab-fixtures.json").read_text()
)
document_id = fixtures["documents"]["alice_doc"]["id"]

with database() as connection:
    row = connection.execute(
        """
        SELECT
            d.id,
            d.owner_id,
            d.tenant_id,
            d.content,
            u.username AS owner_username
        FROM documents AS d
        JOIN users AS u ON u.id = d.owner_id
        WHERE d.id = ?
        """,
        (document_id,),
    ).fetchone()

assert row is not None, "Fixture document does not exist"
ground_truth = dict(row)

assert ground_truth["owner_username"] == "alice"
assert ground_truth["tenant_id"] == "A"

expected_body = {
    key: ground_truth[key]
    for key in ("id", "owner_id", "tenant_id", "content")
}

statuses = {}
for actor in ("alice", "bob", "carol", "anonymous"):
    statuses[actor] = int(
        (evidence / f"day5-{actor}-status.txt").read_text().strip()
    )

assert statuses == {
    "alice": 200,
    "bob": 200,
    "carol": 403,
    "anonymous": 401,
}, statuses

for actor in ("alice", "bob"):
    body = json.loads(
        (evidence / f"day5-{actor}-read.json").read_text()
    )
    assert body == expected_body, (
        f"{actor}: response differs from the actual document"
    )

(evidence / "day5-ground-truth.json").write_text(
    json.dumps(ground_truth, indent=2) + "\n"
)

summary = {
    "scenario": "same_tenant_private_document_read",
    "expected_bob_permission": "DENY",
    "observed_bob_private_content_exposure": True,
    "policy_verdict": "FAIL",
    "controls": {
        "owner_read": "PASS",
        "cross_tenant_denial": "PASS",
        "anonymous_denial": "PASS",
    },
    "http_statuses": statuses,
    "distinct_seeded_defects": 1,
}

(evidence / "day5-summary.json").write_text(
    json.dumps(summary, indent=2) + "\n"
)

print("Database owner: alice; tenant: A")
print("Owner read control: PASS")
print("Cross-tenant denial control: PASS")
print("Anonymous denial control: PASS")
print("Bob response matches actual private document: YES")
print("Bob authorization policy: FAIL")
print("Controlled defect reproduction: PASS")
print("Distinct seeded defects: 1")
