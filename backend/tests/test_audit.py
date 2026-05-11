from __future__ import annotations

from fastapi.testclient import TestClient


def _decision_payload(thesis: str = "tight evening reserve margin") -> dict:
    return {
        "market_code": "ERCOT_NORTH",
        "position_gbp": 10_000,
        "direction": "long",
        "horizon_hours": 24,
        "risk_gbp": 500,
        "likely_gbp": 120,
        "upside_gbp": 800,
        "thesis_text": thesis,
    }


def test_decision_mutations_write_hash_chained_audit(client: TestClient) -> None:
    created = client.post("/api/decisions", json=_decision_payload()).json()
    decision_id = created["id"]
    patch = client.patch(
        f"/api/decisions/{decision_id}",
        json={"thesis_text": "updated thesis"},
    )
    assert patch.status_code == 200
    delete = client.delete(f"/api/decisions/{decision_id}")
    assert delete.status_code == 200

    response = client.get("/api/audit")
    assert response.status_code == 200
    rows = response.json()
    actions = [row["action"] for row in rows]
    assert actions == ["decision.create", "decision.update", "decision.delete"]
    assert all(len(row["signed_hash"]) == 64 for row in rows)
    assert len({row["signed_hash"] for row in rows}) == 3
    assert rows[0]["before"] is None
    assert rows[0]["after"]["id"] == decision_id
    assert rows[1]["before"]["thesis_text"] == "tight evening reserve margin"
    assert rows[1]["after"]["thesis_text"] == "updated thesis"
    assert rows[2]["before"]["id"] == decision_id
    assert rows[2]["after"] is None


def test_audit_export_rejects_invalid_time_range(client: TestClient) -> None:
    response = client.get("/api/audit?from=2026-05-12T00:00:00Z&to=2026-05-11T00:00:00Z")
    assert response.status_code == 400
