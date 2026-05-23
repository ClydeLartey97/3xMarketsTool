# Power BI Implementation Plan

This document defines the Power BI integration work before code changes are made. The goal is to add Power BI where it is genuinely useful: as an embedded analytics surface for richer report consumption, while preserving the native market workbench for live trading, risk, and event workflows.

## Current State

- The application currently has a FastAPI backend and a Next.js frontend.
- Market intelligence is rendered with native React components and charting libraries.
- There is no Power BI dependency, no Power BI REST API usage, and no report embedding surface.
- The backend already owns authenticated API calls, audit logging, market data, forecasts, risk, and report export generation.
- The frontend already has natural analytics entry points: the top navigation, each market workbench, and the developer/API reference page.

## Integration Goals

1. Add an optional Power BI embedded analytics integration.
2. Keep the app fully functional when Power BI is not configured.
3. Never expose Microsoft Entra client secrets or service principal credentials to the browser.
4. Let the backend mint short-lived Power BI embed tokens.
5. Let the frontend render an embedded Power BI report using `powerbi-client`.
6. Filter or contextualize the report by selected market when configured.
7. Document setup, environment variables, endpoint behavior, and verification steps.

## Non-Goals

- Do not replace the existing native dashboard, charts, risk engine, or report exports.
- Do not build or publish a `.pbix` file in this change.
- Do not push app data into Power BI datasets yet. That can be a later workspace/dataset sync project.
- Do not require Power BI credentials for local development or tests.
- Do not add user-owned Power BI OAuth flows. This change uses the "app owns data" embedded analytics pattern via service principal credentials.

## External API Model

The backend will follow Microsoft's embedded analytics model:

- It authenticates to Microsoft Entra ID with client credentials.
- It reads Power BI report metadata from the Power BI REST API.
- It calls the Power BI Generate Token API to create an embed token.
- It returns only browser-safe embed config to the frontend.

Official references:

- Generate an embed token: https://learn.microsoft.com/en-us/power-bi/developer/embedded/generate-embed-token
- Power BI JavaScript report embedding: https://learn.microsoft.com/en-us/javascript/api/overview/powerbi/embed-report
- Power BI REST Generate Token API: https://learn.microsoft.com/en-gb/rest/api/power-bi/embed-token/generate-token

## Environment Variables

Backend settings to add:

- `POWER_BI_TENANT_ID`: Microsoft Entra tenant ID.
- `POWER_BI_CLIENT_ID`: service principal application/client ID.
- `POWER_BI_CLIENT_SECRET`: service principal secret. This remains backend-only.
- `POWER_BI_WORKSPACE_ID`: default Power BI workspace/group ID.
- `POWER_BI_REPORT_ID`: default report ID.
- `POWER_BI_DATASET_ID`: optional semantic model/dataset ID. If omitted, the backend will use the report metadata response when available.
- `POWER_BI_REPORT_MAP_JSON`: optional JSON object mapping market codes to workspace/report/dataset/page overrides.
- `POWER_BI_MARKET_FILTER_TABLE`: optional table name for a client-side market filter.
- `POWER_BI_MARKET_FILTER_COLUMN`: optional column name for a client-side market filter.

Example `POWER_BI_REPORT_MAP_JSON`:

```json
{
  "GB_POWER": {
    "workspace_id": "00000000-0000-0000-0000-000000000000",
    "report_id": "11111111-1111-1111-1111-111111111111",
    "dataset_id": "22222222-2222-2222-2222-222222222222",
    "page_name": "ReportSectionMarket"
  }
}
```

## Backend Design

### New service: `backend/app/services/power_bi.py`

Responsibilities:

1. Determine whether Power BI is configured.
2. Resolve the active report target for a market code.
3. Request an Entra access token with the client credentials grant.
4. Fetch Power BI report metadata, especially `embedUrl`, report name, and dataset ID.
5. Generate a Power BI embed token.
6. Return a normalized embed config response.
7. Return a disabled/setup response when required settings are missing.

Failure behavior:

- Missing configuration returns a successful disabled response with a setup message.
- Microsoft authentication or REST failures raise a controlled HTTP-facing error.
- Secrets are never included in logs or responses.

### New schema models in `backend/app/schemas/domain.py`

Add models for:

- `PowerBIReportTarget`
- `PowerBIEmbedConfig`

The response should include:

- `enabled`
- `configured`
- `market_code`
- `report_id`
- `workspace_id`
- `dataset_id`
- `report_name`
- `embed_url`
- `embed_token`
- `token_type`
- `expires_at`
- `page_name`
- `filter_table`
- `filter_column`
- `reason`

### New API endpoint in `backend/app/api/routes.py`

Add:

- `GET /api/integrations/power-bi/embed-config?market_code=GB_POWER`

Behavior:

- Requires the same app authentication as other protected API endpoints.
- Validates that `market_code` exists when supplied.
- Returns disabled/setup state when Power BI is not configured.
- Returns embed config when configured.
- Auditing is not necessary for every read, but failures must be controlled.

### Backend tests

Add tests for:

1. Missing Power BI config returns `configured=false`.
2. Market-specific report map resolution works without external network calls.
3. Configured endpoint uses mocked Microsoft responses and returns embed-safe values.

## Frontend Design

### Dependency

Add:

- `powerbi-client`

This is the Microsoft-supported browser embedding package.

### Types

Add `PowerBIEmbedConfig` to `frontend/types/domain.ts`.

### API helper

Add `getPowerBIEmbedConfig(marketCode?: string)` to `frontend/lib/api.ts`.

### Embed component

Add `frontend/components/power-bi-report.tsx`.

Responsibilities:

1. Load report config from the backend.
2. Show a compact setup state when Power BI is not configured.
3. Use `powerbi-client` only on the client.
4. Embed a report into a stable-height container.
5. Apply a market filter when `filter_table`, `filter_column`, and `market_code` are present.
6. Reset embedded report instances on unmount to avoid stale iframes.
7. Avoid rendering secrets or backend-only config.

### User-facing surfaces

Add two relevant places:

1. A dedicated `/power-bi` page for the main embedded analytics workspace.
2. A collapsible "Power BI analytics" section in each market workbench, scoped to the selected market.

Add top navigation item:

- `Power BI`

### Developer surface

Add the new integration endpoint and configuration notes to the developer/API page.

## Documentation Updates

Update `README.md` with:

- Power BI setup section.
- Required and optional environment variables.
- New API endpoint.
- Explanation that the integration is optional and disabled by default.

## Verification Plan

Run:

1. Backend targeted tests for the Power BI service/API.
2. Existing backend API tests if targeted tests pass.
3. Frontend lint.
4. Frontend build or type check.
5. Start the frontend/backend if feasible.
6. Open the app in the browser and verify:
   - `/power-bi` renders the setup state without credentials.
   - A market page renders the Power BI section without breaking the existing workbench.
   - No Power BI secret appears in client output.

## Implementation Checklist

- [x] Add backend settings.
- [x] Add backend Power BI schema models.
- [x] Add backend Power BI service.
- [x] Add backend integration endpoint.
- [x] Add backend tests.
- [x] Add frontend dependency.
- [x] Add frontend types and API helper.
- [x] Add Power BI embed component.
- [x] Add `/power-bi` page.
- [x] Add market workbench Power BI section.
- [x] Add nav and developer-page references.
- [x] Update README.
- [x] Run verification.

Verification note:

- Backend Power BI tests passed with `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_power_bi.py -s`.
- Backend Python compile check passed for the Power BI service, route, and schema files.
- Frontend lint/build/browser smoke were attempted. The local Next dev/compiler process stalled while compiling routes in this environment, including a temporary bare `/power-bi` page, so the browser smoke could not complete here.
