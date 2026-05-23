from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.schemas.domain import PowerBIEmbedConfig, PowerBIReportTarget

ENTRA_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
POWER_BI_API_BASE = "https://api.powerbi.com/v1.0/myorg"


class PowerBIIntegrationError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _secret_value(settings: Settings) -> str:
    return settings.power_bi_client_secret.get_secret_value()


def _required_credential_gaps(settings: Settings) -> list[str]:
    gaps: list[str] = []
    if not settings.power_bi_tenant_id:
        gaps.append("POWER_BI_TENANT_ID")
    if not settings.power_bi_client_id:
        gaps.append("POWER_BI_CLIENT_ID")
    if not _secret_value(settings):
        gaps.append("POWER_BI_CLIENT_SECRET")
    return gaps


def _parse_report_map(settings: Settings) -> dict[str, Any]:
    raw = settings.power_bi_report_map_json.strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PowerBIIntegrationError("POWER_BI_REPORT_MAP_JSON is not valid JSON.", status_code=500) from exc
    if not isinstance(parsed, dict):
        raise PowerBIIntegrationError("POWER_BI_REPORT_MAP_JSON must be a JSON object.", status_code=500)
    return parsed


def _entry_value(entry: dict[str, Any], snake_key: str, camel_key: str) -> str | None:
    value = entry.get(snake_key, entry.get(camel_key))
    return str(value) if value else None


def resolve_power_bi_report_target(
    settings: Settings | None = None,
    market_code: str | None = None,
) -> tuple[PowerBIReportTarget | None, list[str]]:
    """Resolve the report target and return missing configuration names.

    This is intentionally pure so tests can cover market-specific mapping
    without touching Microsoft services.
    """
    settings = settings or get_settings()
    report_map = _parse_report_map(settings)
    market_entry: dict[str, Any] = {}
    if market_code:
        raw_entry = report_map.get(market_code) or report_map.get(market_code.upper())
        if raw_entry is not None and not isinstance(raw_entry, dict):
            raise PowerBIIntegrationError(
                f"POWER_BI_REPORT_MAP_JSON entry for {market_code} must be an object.",
                status_code=500,
            )
        market_entry = raw_entry or {}

    workspace_id = _entry_value(market_entry, "workspace_id", "workspaceId") or settings.power_bi_workspace_id
    report_id = _entry_value(market_entry, "report_id", "reportId") or settings.power_bi_report_id
    dataset_id = _entry_value(market_entry, "dataset_id", "datasetId") or settings.power_bi_dataset_id or None
    page_name = _entry_value(market_entry, "page_name", "pageName")

    gaps = _required_credential_gaps(settings)
    if not workspace_id:
        gaps.append("POWER_BI_WORKSPACE_ID")
    if not report_id:
        gaps.append("POWER_BI_REPORT_ID")
    if gaps:
        return None, gaps

    return (
        PowerBIReportTarget(
            workspace_id=workspace_id,
            report_id=report_id,
            dataset_id=dataset_id,
            page_name=page_name,
        ),
        [],
    )


def _disabled_config(market_code: str | None, gaps: list[str]) -> PowerBIEmbedConfig:
    missing = ", ".join(gaps)
    return PowerBIEmbedConfig(
        enabled=False,
        configured=False,
        market_code=market_code,
        reason=f"Power BI is not configured. Missing: {missing}.",
    )


def _request_entra_token(client: httpx.Client, settings: Settings) -> str:
    url = f"https://login.microsoftonline.com/{settings.power_bi_tenant_id}/oauth2/v2.0/token"
    response = client.post(
        url,
        data={
            "client_id": settings.power_bi_client_id,
            "client_secret": _secret_value(settings),
            "grant_type": "client_credentials",
            "scope": ENTRA_SCOPE,
        },
    )
    if response.status_code >= 400:
        raise PowerBIIntegrationError("Power BI authentication failed.")
    token = response.json().get("access_token")
    if not token:
        raise PowerBIIntegrationError("Power BI authentication response did not include an access token.")
    return str(token)


def _request_report_metadata(
    client: httpx.Client,
    access_token: str,
    target: PowerBIReportTarget,
) -> dict[str, Any]:
    response = client.get(
        f"{POWER_BI_API_BASE}/groups/{target.workspace_id}/reports/{target.report_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code >= 400:
        raise PowerBIIntegrationError("Power BI report metadata request failed.")
    body = response.json()
    if not body.get("embedUrl"):
        raise PowerBIIntegrationError("Power BI report metadata response did not include an embed URL.")
    return body


def _request_embed_token(
    client: httpx.Client,
    access_token: str,
    target: PowerBIReportTarget,
    dataset_id: str | None,
) -> tuple[str, datetime | None]:
    payload: dict[str, Any] = {"reports": [{"id": target.report_id}]}
    if dataset_id:
        payload["datasets"] = [{"id": dataset_id}]
    response = client.post(
        f"{POWER_BI_API_BASE}/GenerateToken",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if response.status_code >= 400:
        raise PowerBIIntegrationError("Power BI embed-token request failed.")
    body = response.json()
    token = body.get("token")
    if not token:
        raise PowerBIIntegrationError("Power BI embed-token response did not include a token.")
    expiration = body.get("expiration")
    return str(token), datetime.fromisoformat(expiration.replace("Z", "+00:00")) if expiration else None


def build_power_bi_embed_config(
    market_code: str | None = None,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> PowerBIEmbedConfig:
    settings = settings or get_settings()
    target, gaps = resolve_power_bi_report_target(settings, market_code)
    if gaps or target is None:
        return _disabled_config(market_code, gaps)

    owns_client = client is None
    http_client = client or httpx.Client(timeout=15.0)
    try:
        access_token = _request_entra_token(http_client, settings)
        metadata = _request_report_metadata(http_client, access_token, target)
        dataset_id = target.dataset_id or metadata.get("datasetId")
        embed_token, expires_at = _request_embed_token(http_client, access_token, target, dataset_id)
    finally:
        if owns_client:
            http_client.close()

    filter_table = settings.power_bi_market_filter_table or None
    filter_column = settings.power_bi_market_filter_column or None
    return PowerBIEmbedConfig(
        enabled=True,
        configured=True,
        market_code=market_code,
        workspace_id=target.workspace_id,
        report_id=target.report_id,
        dataset_id=dataset_id,
        report_name=metadata.get("name"),
        embed_url=metadata.get("embedUrl"),
        embed_token=embed_token,
        expires_at=expires_at,
        page_name=target.page_name,
        filter_table=filter_table if filter_column else None,
        filter_column=filter_column if filter_table else None,
    )

