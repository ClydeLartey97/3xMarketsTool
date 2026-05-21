from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.auth import create_access_token, hash_password


def _payload() -> dict:
    return {
        "market_code": "ERCOT_NORTH",
        "position_gbp": 10_000,
        "direction": "long",
        "horizon_hours": 6,
        "n_paths": 500,
    }


def _auditor_headers(db: Session) -> dict[str, str]:
    user = User(
        email="export-auditor@3x.local",
        password_hash=hash_password("export-auditor-password"),
        organisation="3x Test",
        role="auditor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_risk_export_pdf(client: TestClient) -> None:
    response = client.post("/api/risk-assessment/export?format=pdf", json=_payload())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_risk_export_xlsx_and_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post("/api/risk-assessment/export?format=xlsx", json=_payload())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content.startswith(b"PK")

    audit = client.get("/api/audit", headers=_auditor_headers(db_session))
    assert audit.status_code == 200
    assert audit.json()[-1]["action"] == "risk.export"
