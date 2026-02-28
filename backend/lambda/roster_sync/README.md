# Roster Sync Lambda (30-minute scheduler)

This Lambda calls your backend endpoint `POST /api/v1/roster/sync` every 30 minutes using EventBridge.

## 1) Prerequisites

- AWS account with access to deploy Lambda/EventBridge in Mumbai (`ap-south-1`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Backend API reachable from the Lambda (public URL or private networking)

## 2) Deploy

Run from this folder:

```bash
cd /Users/niranjanaambadi/Documents/latest_lawmate/backend/lambda/roster_sync
sam build
sam deploy --guided
```

During `sam deploy --guided`, provide:

- `RosterSyncUrl`: your live backend endpoint, e.g. `https://api.yourdomain.com/api/v1/roster/sync`
- `RosterSyncBearerToken`: optional token if endpoint is protected
- `RosterSyncApiKey`: optional key if endpoint is protected
- Region: `ap-south-1`

The template already creates the schedule: `rate(30 minutes)`.

## 3) Test once

After deploy:

```bash
aws lambda invoke \
  --function-name lawmate-roster-sync \
  --region ap-south-1 \
  --payload '{}' \
  /tmp/roster-sync-response.json && cat /tmp/roster-sync-response.json
```

## 4) Where roster is saved in S3

Based on current backend settings (`ROSTER_S3_BUCKET_NAME=lawmate-khc-prod`, `ROSTER_S3_PREFIX=roster`):

- Latest PDF: `s3://lawmate-khc-prod/roster/latest.pdf`
- Latest metadata: `s3://lawmate-khc-prod/roster/latest.json`
- Archived PDFs: `s3://lawmate-khc-prod/roster/<YYYY-MM-DD>/<filename>.pdf`

Example archive key:
`s3://lawmate-khc-prod/roster/2026-02-14/roster_14_02_2026.pdf`
