# Atlas Trigger Cluster Scaling Demo

This repository demonstrates one practical pattern for scheduled Atlas cluster scaling:

1. Use **MongoDB Atlas Scheduled Triggers** with **CRON** for calendar-based scheduling (for example, specific days of the month).
2. Have each trigger call a webhook endpoint.
3. Run Python scripts behind those webhook endpoints to scale a cluster up or down via the Atlas Admin API.

This is useful for prospects that need temporary capacity windows (billing cycles, monthly batch jobs, launch events) and want to automatically scale back down afterward.

## What You Get

- `scripts/scale_up_trigger.py`: scales to a higher tier (for example `M50`).
- `scripts/scale_down_trigger.py`: scales back down (for example `M10`).

Both scripts use environment variables so you can change project, cluster, and tiers without code edits.

## Prerequisites

- Atlas project with an existing cluster.
- Atlas Programmatic API key with permissions to modify clusters.
- Python 3.9+.
- `requests` package.

Install dependency:

```bash
pip install requests
```

## Environment Variables

Set these in the runtime where your scripts execute (Lambda, Cloud Run, VM, etc.).

```bash
export ATLAS_PUBLIC_KEY="<atlas-api-public-key>"
export ATLAS_PRIVATE_KEY="<atlas-api-private-key>"
export ATLAS_PROJECT_ID="<atlas-project-id>"
export ATLAS_CLUSTER_NAME="<atlas-cluster-name>"

# Tier used by scale_up_trigger.py
export SCALE_UP_TIER="M50"

# Tier used by scale_down_trigger.py
export SCALE_DOWN_TIER="M10"
```

Optional:

```bash
export ATLAS_BASE_URL="https://cloud.mongodb.com/api/atlas/v2"
```

## Test Locally

Scale up:

```bash
python scripts/scale_up_trigger.py
```

Scale down:

```bash
python scripts/scale_down_trigger.py
```

## Atlas Trigger Design

Atlas Scheduled Triggers run JavaScript functions. A common architecture is:

- **Scheduled Trigger (CRON)**
- Atlas Function performs an HTTP call to your Python webhook
- Python script updates cluster tier through Atlas Admin API

### Example CRON Schedules

- Scale up on the 1st of each month at 12:00 UTC: `0 12 1 * *`
- Scale down on the 3rd of each month at 02:00 UTC: `0 2 3 * *`

### Example Atlas Function (Scale Up Trigger)

Use this as the trigger function body in Atlas App Services:

```javascript
exports = async function() {
  const response = await context.http.post({
    url: context.values.get("SCALE_UP_WEBHOOK_URL"),
    headers: { "Content-Type": ["application/json"] },
    body: JSON.stringify({ source: "atlas-scheduled-trigger", action: "scale-up" })
  });

  if (response.statusCode >= 300) {
    throw new Error(`Scale-up webhook failed: ${response.statusCode}`);
  }
};
```

### Example Atlas Function (Scale Down Trigger)

```javascript
exports = async function() {
  const response = await context.http.post({
    url: context.values.get("SCALE_DOWN_WEBHOOK_URL"),
    headers: { "Content-Type": ["application/json"] },
    body: JSON.stringify({ source: "atlas-scheduled-trigger", action: "scale-down" })
  });

  if (response.statusCode >= 300) {
    throw new Error(`Scale-down webhook failed: ${response.statusCode}`);
  }
};
```

Store webhook URLs as Atlas Values/Secrets (`SCALE_UP_WEBHOOK_URL`, `SCALE_DOWN_WEBHOOK_URL`).

## API Behavior Notes

- Atlas scaling is asynchronous. The API returns quickly while the cluster transitions.
- Avoid overlapping triggers.
- Give enough time between scale-up and scale-down windows for your workload.

## Security Notes

- Never hardcode API keys in source code.
- Use least-privilege API keys.
- Restrict webhook access (shared secret, IP allowlist, IAM, etc.).

## Demo Flow

1. Set `SCALE_UP_TIER` and `SCALE_DOWN_TIER` to your demo tiers.
2. Configure two Atlas Scheduled Triggers with CRON expressions.
3. Trigger scale-up for known peak window dates.
4. Trigger scale-down after the window.
5. Observe tier changes in Atlas UI and correlate with workload/latency metrics.

