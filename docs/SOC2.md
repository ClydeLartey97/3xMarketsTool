# SOC2 Preparation

This document maps the current Frontier hardening work to SOC2-ready operating controls. It is not a completed SOC2 program; it is the implementation baseline and evidence checklist for an eventual audit.

## Audit Log

- All API mutations should write an `audit_log` row with `actor`, `action`, `target`, `before`, `after`, and `signed_hash`.
- `signed_hash` forms a tamper-evident hash chain by incorporating the previous row hash.
- Compliance export is available at `GET /api/audit?from=&to=` for authenticated users.
- Evidence to retain: migration history, sample export, hash-chain verification script output, and access review showing who can call audit export.

## Encryption

- In transit: production deployments must terminate HTTPS/WSS at the load balancer or reverse proxy. Internal Compose traffic is plain HTTP and intended for a trusted single-host deployment only.
- At rest: Postgres volume encryption must be provided by the host/cloud disk layer. Redis persistence is enabled in Compose and should also sit on encrypted storage.
- Backups: database and report backups should inherit the same encrypted storage policy and be access-controlled separately from application runtime access.

## Secret Management

- Required runtime secrets include `JWT_SECRET`, database credentials, Redis credentials when enabled, API keys such as `EIA_API_KEY`, optional LLM provider keys, and any OTLP credentials.
- Local `.env` files are not committed. Production should load secrets from the deployment platform secret store, not from baked images.
- Rotate `JWT_SECRET` and third-party API keys on personnel changes, suspected exposure, or at a defined rotation interval.
- Evidence to retain: secret inventory, rotation log, and deployment configuration showing secrets are injected at runtime.

## Access Control

- API routes are protected with bearer JWT auth, except health, auth bootstrap, and the market websocket stream.
- Decisions and open positions are scoped by `user_id`; user A cannot read or mutate user B decisions.
- Default roles are currently coarse (`analyst`, seeded demo user). Before external enterprise use, define role permissions for admin, analyst, auditor, and read-only users.
- Evidence to retain: auth tests, user access review, and screenshots/API transcripts proving cross-user isolation.

## Change Management

- Database changes are managed with Alembic revisions under `backend/alembic`.
- Application changes should be committed with phase-scoped messages and tested before merge/deploy.
- `make deploy` builds and starts the Compose stack; backend startup runs Alembic migrations before Uvicorn.
- Evidence to retain: pull requests, test output, migration revision history, deployment logs, and rollback notes for material changes.

## Observability

- Backend logs are structured JSON via structlog.
- OpenTelemetry instruments FastAPI, SQLAlchemy, and httpx. Console export is the default; OTLP export is enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- Compose includes an OpenTelemetry collector exposing OTLP gRPC on `4317` and HTTP on `4318`.
- Evidence to retain: sample trace, log sample with request/error context, and alerting rules once an observability backend is attached.

## Incident Response Stub

1. Triage: identify severity, affected markets/users/data, and whether trading decisions could be impacted.
2. Contain: revoke exposed secrets, disable affected accounts, pause workers if data integrity is at risk, and snapshot logs/database state.
3. Eradicate: patch the root cause, run migrations or data repair scripts when required, and rotate credentials.
4. Recover: redeploy, verify health checks, replay or backfill workers, and confirm audit-log continuity.
5. Communicate: notify affected users and vendors according to contractual timelines.
6. Review: write a post-incident report with timeline, root cause, customer impact, and follow-up owners.

## Vendor List

| Vendor | Purpose | Data Shared | Notes |
| --- | --- | --- | --- |
| PostgreSQL | Primary relational database | Application data, users, decisions, audit log | Self-hosted in Compose or managed equivalent. |
| Redis | Worker queue and market pub/sub | Job metadata, transient market stream messages | Compose uses append-only persistence. |
| OpenTelemetry Collector | Trace/log/metric routing | Telemetry metadata | Debug exporter in local Compose; attach OTLP backend in production. |
| EIA | U.S. market data | API key, public market queries | Optional; app degrades without key. |
| Open-Meteo | Weather data | Public weather coordinates | No user data. |
| ELEXON BMRS | GB power prices | Public market queries | No user data. |
| Yahoo Finance via yfinance | Gas reference prices | Public ticker queries | No user data. |
| Gemini / Domain LLM provider | Optional news scoring | News text, market context | Use only with approved provider terms and data handling. |

## Pre-Audit Gaps

- Add formal role-based permissions beyond the current coarse user role.
- Add automated audit hash-chain verification and scheduled evidence export.
- Add managed TLS and encrypted backups in the target production environment.
- Define retention periods for logs, reports, decisions, and audit rows.
- Complete vendor DPAs/security reviews for any hosted LLM or telemetry backend.
