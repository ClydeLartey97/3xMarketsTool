import json
from urllib.parse import parse_qsl

import httpx

from app.core.config import Settings, get_settings
from app.services.power_bi import ENTRA_SCOPE, build_power_bi_embed_config, resolve_power_bi_report_target


POWER_BI_ENV_VARS = [
    "POWER_BI_TENANT_ID",
    "POWER_BI_CLIENT_ID",
    "POWER_BI_CLIENT_SECRET",
    "POWER_BI_WORKSPACE_ID",
    "POWER_BI_REPORT_ID",
    "POWER_BI_DATASET_ID",
    "POWER_BI_REPORT_MAP_JSON",
]

POWER_BI_SETTING_ALIASES = {
    "power_bi_tenant_id": "POWER_BI_TENANT_ID",
    "power_bi_client_id": "POWER_BI_CLIENT_ID",
    "power_bi_client_secret": "POWER_BI_CLIENT_SECRET",
    "power_bi_workspace_id": "POWER_BI_WORKSPACE_ID",
    "power_bi_report_id": "POWER_BI_REPORT_ID",
    "power_bi_dataset_id": "POWER_BI_DATASET_ID",
    "power_bi_report_map_json": "POWER_BI_REPORT_MAP_JSON",
    "power_bi_market_filter_table": "POWER_BI_MARKET_FILTER_TABLE",
    "power_bi_market_filter_column": "POWER_BI_MARKET_FILTER_COLUMN",
}


def _settings(**overrides) -> Settings:
    defaults = {
        "POWER_BI_TENANT_ID": "tenant-id",
        "POWER_BI_CLIENT_ID": "client-id",
        "POWER_BI_CLIENT_SECRET": "client-secret",
        "POWER_BI_WORKSPACE_ID": "workspace-default",
        "POWER_BI_REPORT_ID": "report-default",
    }
    defaults.update({POWER_BI_SETTING_ALIASES.get(key, key): value for key, value in overrides.items()})
    return Settings(**defaults)


def test_power_bi_embed_config_endpoint_disabled_without_settings(client, monkeypatch) -> None:
    for env_var in POWER_BI_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)
    get_settings.cache_clear()

    response = client.get(
        "/api/integrations/power-bi/embed-config",
        params={"market_code": "ERCOT_NORTH"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["configured"] is False
    assert body["market_code"] == "ERCOT_NORTH"
    assert "POWER_BI_TENANT_ID" in body["reason"]
    get_settings.cache_clear()


def test_power_bi_report_map_resolves_market_specific_target() -> None:
    settings = _settings(
        power_bi_report_map_json=json.dumps(
            {
                "GB_POWER": {
                    "workspace_id": "workspace-gb",
                    "report_id": "report-gb",
                    "dataset_id": "dataset-gb",
                    "page_name": "ReportSectionGB",
                }
            }
        )
    )

    target, gaps = resolve_power_bi_report_target(settings, "GB_POWER")
    default_target, default_gaps = resolve_power_bi_report_target(settings, "ERCOT_NORTH")

    assert gaps == []
    assert target is not None
    assert target.workspace_id == "workspace-gb"
    assert target.report_id == "report-gb"
    assert target.dataset_id == "dataset-gb"
    assert target.page_name == "ReportSectionGB"
    assert default_gaps == []
    assert default_target is not None
    assert default_target.workspace_id == "workspace-default"
    assert default_target.report_id == "report-default"


def test_power_bi_embed_config_uses_microsoft_responses_without_exposing_credentials() -> None:
    settings = _settings(
        power_bi_workspace_id="workspace-1",
        power_bi_report_id="report-1",
        power_bi_market_filter_table="Markets",
        power_bi_market_filter_column="MarketCode",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            form = dict(parse_qsl(request.content.decode()))
            assert form["client_secret"] == "client-secret"
            assert form["grant_type"] == "client_credentials"
            assert form["scope"] == ENTRA_SCOPE
            return httpx.Response(200, json={"access_token": "entra-token"})

        assert request.headers["authorization"] == "Bearer entra-token"
        if request.method == "GET" and request.url.path == "/v1.0/myorg/groups/workspace-1/reports/report-1":
            return httpx.Response(
                200,
                json={
                    "id": "report-1",
                    "name": "Market Intelligence",
                    "embedUrl": "https://app.powerbi.com/reportEmbed?reportId=report-1",
                    "datasetId": "dataset-from-report",
                },
            )

        if request.method == "POST" and request.url.path == "/v1.0/myorg/GenerateToken":
            assert json.loads(request.content.decode()) == {
                "reports": [{"id": "report-1"}],
                "datasets": [{"id": "dataset-from-report"}],
            }
            return httpx.Response(
                200,
                json={"token": "embed-token", "expiration": "2026-05-24T00:00:00Z"},
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    config = build_power_bi_embed_config("GB_POWER", settings=settings, client=http_client)

    assert config.enabled is True
    assert config.configured is True
    assert config.market_code == "GB_POWER"
    assert config.workspace_id == "workspace-1"
    assert config.report_id == "report-1"
    assert config.dataset_id == "dataset-from-report"
    assert config.report_name == "Market Intelligence"
    assert config.embed_url == "https://app.powerbi.com/reportEmbed?reportId=report-1"
    assert config.embed_token == "embed-token"
    assert config.filter_table == "Markets"
    assert config.filter_column == "MarketCode"
    assert "client-secret" not in config.model_dump_json()
