# Live Status Sync Lambda (15-minute scheduler)

This Lambda calls your backend endpoint:

- `POST /api/v1/live-status-worker/run-due?batch_size=<n>`

It should run every 15 minutes and process due cases in round-robin batches.

## 1) Backend prerequisites

Set these in backend `.env` / deployment env:

- `MCP_WORKER_TOKEN=<strong-random-secret>`
- Optional MCP upstream integration:
  - `MCP_LIVE_STATUS_URL=<your mcp endpoint>`
  - `MCP_LIVE_STATUS_TOKEN=<bearer token for mcp>`

Apply DB migration:

```bash
cd /Users/niranjanaambadi/Documents/latest_lawmate/backend
psql "$DATABASE_URL" -f database/live_status_migration.sql
```

## 2) Deploy Lambda (ap-south-1)

```bash
cd /Users/niranjanaambadi/Documents/latest_lawmate/backend/lambda/live_status_sync
sam build
sam deploy --guided
```

Guided values:

- `LiveStatusWorkerUrl`: `https://<api-domain>/api/v1/live-status-worker/run-due`
- `LiveStatusWorkerToken`: same as backend `MCP_WORKER_TOKEN`
- `LiveStatusBatchSize`: e.g. `50`
- Region: `ap-south-1`

## 3) Test once

```bash
aws lambda invoke \
  --function-name lawmate-live-status-sync \
  --region ap-south-1 \
  --payload '{}' \
  /tmp/live-status-sync-response.json && cat /tmp/live-status-sync-response.json
```

