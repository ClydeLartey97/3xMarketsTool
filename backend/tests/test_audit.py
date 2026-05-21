from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.auth import create_access_token, hash_password


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


def _auditor_headers(db: Session) -> dict[str, str]:
    user = User(
        email="auditor@3x.local",
        password_hash=hash_password("auditor-password"),
        organisation="3x Test",
        role="auditor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_decision_mutations_write_hash_chained_audit(
    anon_client: TestClient,
    db_session: Session,
) -> None:
    headers = _auditor_headers(db_session)
    created = anon_client.post("/api/decisions", json=_decision_payload(), headers=headers).json()
    decision_id = created["id"]
    patch = anon_client.patch(
        f"/api/decisions/{decision_id}",
        json={"thesis_text": "updated thesis"},
        headers=headers,
    )
    assert patch.status_code == 200
    delete = anon_client.delete(f"/api/decisions/{decision_id}", headers=headers)
    assert delete.status_code == 200

    response = anon_client.get("/api/audit", headers=headers)
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


def test_audit_export_rejects_invalid_time_range(
    anon_client: TestClient,
    db_session: Session,
) -> None:
    response = anon_client.get(
        "/api/audit?from=2026-05-12T00:00:00Z&to=2026-05-11T00:00:00Z",
        headers=_auditor_headers(db_session),
    )
    assert response.status_code == 400


def test_audit_export_requires_auditor_role(client: TestClient) -> None:
    response = client.get("/api/audit")
    assert response.status_code == 403
