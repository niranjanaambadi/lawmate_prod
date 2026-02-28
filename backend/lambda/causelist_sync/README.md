# Cause List Sync Lambda (2-hour scheduler)

This Lambda calls your backend endpoint `POST /api/v1/causelist/sync` every 2 hours.

## 1) Deploy

```bash
cd /Users/niranjanaambadi/Documents/latest_lawmate/backend/lambda/causelist_sync
sam build
sam deploy --guided
```

During guided deploy:

- `CauseListSyncUrl`: e.g. `https://api.yourdomain.com/api/v1/causelist/sync`
- `CauseListSyncSource`: usually `daily` (or `all` if you configure all source URLs)
- `CauseListSyncBearerToken`: optional
- `CauseListSyncApiKey`: optional
- Region: `ap-south-1`

The schedule is in template: `rate(2 hours)`.

## 2) Test once

```bash
aws lambda invoke \
  --function-name lawmate-causelist-sync \
  --region ap-south-1 \
  --payload '{}' \
  /tmp/causelist-sync-response.json && cat /tmp/causelist-sync-response.json
```

## 3) S3 raw payload location

By default (`CAUSELIST_S3_BUCKET_NAME=lawmate-khc-prod`, `CAUSELIST_S3_PREFIX=causelist`):

- `s3://lawmate-khc-prod/causelist/raw-pdf/source=<source>/listing_date=<YYYY-MM-DD>/fetched_at=<timestamp>/host=<host>/<file>.pdf`

Each fetched PDF becomes a separate ingestion run in DB with the associated `s3_key`.
