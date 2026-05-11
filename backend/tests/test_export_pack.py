from __future__ import annotations

from fastapi.testclient import TestClient


def _payload() -> dict:
    return {
        "market_code": "ERCOT_NORTH",
        "position_gbp": 10_000,
        "direction": "long",
        "horizon_hours": 6,
        "n_paths": 500,
    }


def test_risk_export_pdf(client: TestClient) -> None:
    response = client.post("/api/risk-assessment/export?format=pdf", json=_payload())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_risk_export_xlsx_and_audit(client: TestClient) -> None:
    response = client.post("/api/risk-assessment/export?format=xlsx", json=_payload())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content.startswith(b"PK")

    audit = client.get("/api/audit")
    assert audit.status_code == 200
    assert audit.json()[-1]["action"] == "risk.export"
