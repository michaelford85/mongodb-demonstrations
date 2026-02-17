# Atlas Trigger Cluster Scaling Demo

This repository demonstrates practical patterns for scheduled Atlas cluster scaling:

1. Use **MongoDB Atlas Scheduled Triggers** with **CRON** for calendar-based scheduling (for example, specific days of the month).
2. Run trigger functions that call the Atlas Admin API directly to scale a cluster up or down.
3. Optionally use Python scripts in this repo when you want an external runtime pattern.

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

## Atlas Trigger Design (Direct, No Webhook)

Atlas Scheduled Triggers run JavaScript functions. In this pattern:

- **Scheduled Trigger (CRON)**
- Atlas Function calls the Atlas Admin API directly
- Cluster tier is set from Atlas Values/Secrets

### Example CRON Schedules

- Scale up on the 1st of each month at 12:00 UTC: `0 12 1 * *`
- Scale down on the 3rd of each month at 02:00 UTC: `0 2 3 * *`

### Example Atlas Function (Scale Up Trigger)

Use this as the trigger function body in Atlas App Services:

```javascript
exports = async function() {
  const projectId = context.values.get("ATLAS_PROJECT_ID");
  const clusterName = context.values.get("ATLAS_CLUSTER_NAME");
  const targetTier = context.values.get("SCALE_UP_TIER");
  const token = context.values.get("ATLAS_ADMIN_API_TOKEN");
  const baseUrl = context.values.get("ATLAS_BASE_URL") || "https://cloud.mongodb.com/api/atlas/v2";

  const response = await context.http.patch({
    url: `${baseUrl}/groups/${projectId}/clusters/${clusterName}`,
    headers: {
      Authorization: [`Bearer ${token}`],
      "Content-Type": ["application/json"],
      Accept: ["application/vnd.atlas.2024-08-05+json"]
    },
    body: JSON.stringify({
      providerSettings: {
        instanceSizeName: targetTier
      }
    })
  });

  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error(`Scale-up failed: ${response.statusCode} ${response.body.text()}`);
  }
};
```

### Example Atlas Function (Scale Down Trigger)

```javascript
exports = async function() {
  const projectId = context.values.get("ATLAS_PROJECT_ID");
  const clusterName = context.values.get("ATLAS_CLUSTER_NAME");
  const targetTier = context.values.get("SCALE_DOWN_TIER");
  const token = context.values.get("ATLAS_ADMIN_API_TOKEN");
  const baseUrl = context.values.get("ATLAS_BASE_URL") || "https://cloud.mongodb.com/api/atlas/v2";

  const response = await context.http.patch({
    url: `${baseUrl}/groups/${projectId}/clusters/${clusterName}`,
    headers: {
      Authorization: [`Bearer ${token}`],
      "Content-Type": ["application/json"],
      Accept: ["application/vnd.atlas.2024-08-05+json"]
    },
    body: JSON.stringify({
      providerSettings: {
        instanceSizeName: targetTier
      }
    })
  });

  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error(`Scale-down failed: ${response.statusCode} ${response.body.text()}`);
  }
};
```

Store these in Atlas Values/Secrets:

- `ATLAS_PROJECT_ID`
- `ATLAS_CLUSTER_NAME`
- `SCALE_UP_TIER`
- `SCALE_DOWN_TIER`
- `ATLAS_ADMIN_API_TOKEN` (secret)
- `ATLAS_BASE_URL` (optional, default shown above)

## API Behavior Notes

- Atlas scaling is asynchronous. The API returns quickly while the cluster transitions.
- Avoid overlapping triggers.
- Give enough time between scale-up and scale-down windows for your workload.

## Security Notes

- Never hardcode API keys in source code.
- Use least-privilege service account/token scopes.
- Keep `ATLAS_ADMIN_API_TOKEN` in Atlas Secrets.

## Demo Flow

1. Set `SCALE_UP_TIER` and `SCALE_DOWN_TIER` to your demo tiers.
2. Configure two Atlas Scheduled Triggers with CRON expressions.
3. Trigger scale-up for known peak window dates.
4. Trigger scale-down after the window.
5. Observe tier changes in Atlas UI and correlate with workload/latency metrics.
