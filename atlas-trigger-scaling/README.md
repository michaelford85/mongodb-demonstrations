# Atlas Trigger Cluster Scaling Demo

This repository demonstrates practical patterns for scheduled Atlas cluster scaling:

1. Use **[MongoDB Atlas Scheduled Triggers](https://www.mongodb.com/docs/atlas/atlas-ui/triggers/)** with **CRON** for calendar-based scheduling (for example, specific days of the month).
2. Run trigger functions that call the Atlas Admin API directly to scale a cluster up or down.

This is useful for organizations that need temporary capacity windows (billing cycles, monthly batch jobs, launch events) and want to automatically scale back down afterward.

## Prerequisites

- Atlas project with an existing cluster.
- Atlas **[Service Account](https://www.mongodb.com/docs/cloud-manager/tutorial/manage-programmatic-api-keys/)** with Project Owner or Project Cluster Manager role.
- Service Account Client ID and Client Secret.
- (Optional) Python 3.9+ if using the external scripts.

> ⚠️ Atlas Admin API v2 does NOT support Project "Applications" API Keys.
> Use a Service Account (OAuth2) or Org Programmatic API Keys.

## Atlas Trigger Values and Secrets

In order to avoid hardcoding values and sensitive credentials into the Trigger javasript code, you can add values and secrets to your MongoDB Atlas project. 

For thos example, store these in [Atlas Values/Secrets](https://www.mongodb.com/docs/atlas/atlas-ui/triggers/functions/values/#define-and-access-values):

Secrets:
- `ATLAS_SA_CLIENT_ID`
- `ATLAS_SA_CLIENT_Secret`
Values: 
- `ATLAS_SA_CLIENT_ID_VALUE`   (Value linked to secret `ATLAS_SA_CLIENT_ID`)
- `ATLAS_SA_CLIENT_SECRET_VALUE`  (Value linked to Secret `ATLAS_SA_CLIENT_SECRET`)
- `ATLAS_PROJECT_ID`
- `ATLAS_CLUSTER_NAME`
- `SCALE_UP_TIER` The target tier to scale up to for batch jobs
- `SCALE_DOWN_TIER` The target tier to scale back down to
- `ATLAS_BASE_URL` (optional, default value is `https://cloud.mongodb.com/api/atlas/v2`)

⚠️ In App Services, Functions cannot read Secrets directly.
Create a **Value** that links to the Secret, and read that Value.

## Why Use Service Accounts?

Atlas Admin API v2 requires one of:

- Service Account (OAuth2 client credentials)
- Org-level Programmatic API Key (HTTP Digest)

Project-level "Applications" API Keys DO NOT work for cluster administration.

Service Accounts are the recommended modern approach.

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
exports = async function () {
  const projectId   = context.values.get("ATLAS_PROJECT_ID");
  const clusterName = context.values.get("ATLAS_CLUSTER_NAME");
  const targetTier  = context.values.get("SCALE_UP_TIER");
  const baseUrl     = context.values.get("ATLAS_BASE_URL") || "https://cloud.mongodb.com/api/atlas/v2";

  const clientId = context.values.get("ATLAS_SA_CLIENT_ID_VALUE");
  const clientSecret = context.values.get("ATLAS_SA_CLIENT_SECRET_VALUE"); // Value linked to Secret
  
  if (!clientId || !clientSecret) {
    return {
      ok: false,
      clientIdPresent: !!clientId,
      clientSecretLength: (clientSecret || "").length,
      hint: "Make sure both are Values, and secret value is linked to the Secret.",
    };
  }
  
  // Basic auth header
  const basic = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");
  
  const tokenResp = await context.http.post({
    url: "https://cloud.mongodb.com/api/oauth/token",
    headers: {
      Authorization: [`Basic ${basic}`],
      "Content-Type": ["application/x-www-form-urlencoded"],
      Accept: ["application/json"],
    },
    body: "grant_type=client_credentials",
  });
  
  const tokenBody = tokenResp.body ? tokenResp.body.text() : "";
  
  if (tokenResp.statusCode < 200 || tokenResp.statusCode >= 300) {
    throw new Error(`Token request failed: ${tokenResp.statusCode} ${tokenBody}`);
  }
  
  const { access_token } = JSON.parse(tokenBody);

  // 2) GET current cluster so we can preserve replicationSpecs shape
  const clusterUrl = `${baseUrl}/groups/${projectId}/clusters/${clusterName}`;

  const getResp = await context.http.get({
    url: clusterUrl,
    headers: {
      Authorization: [`Bearer ${access_token}`],
      Accept: ["application/vnd.atlas.2024-10-23+json"],
    },
  });

  const getBody = getResp.body ? getResp.body.text() : "";
  if (getResp.statusCode < 200 || getResp.statusCode >= 300) {
    throw new Error(`GET cluster failed: ${getResp.statusCode} ${getBody}`);
  }

  const cluster = JSON.parse(getBody);
  const repl = cluster.replicationSpecs || cluster.effectiveReplicationSpecs;
  if (!repl?.length) throw new Error("No replicationSpecs found on cluster");

  // Remove effective* fields and update instanceSize on any node types present
  const stripReadonly = (obj) => {
    if (Array.isArray(obj)) return obj.map(stripReadonly);
    if (obj && typeof obj === "object") {
      const out = {};
      for (const [k, v] of Object.entries(obj)) {
        if (k.startsWith("effective")) continue;
        if (k === "links") continue;
        out[k] = stripReadonly(v);
      }
      return out;
    }
    return obj;
  };

  const rs0 = stripReadonly(repl[0]);

  for (const rc of (rs0.regionConfigs || [])) {
    for (const key of ["electableSpecs", "analyticsSpecs", "readOnlySpecs"]) {
      if (rc[key]) rc[key].instanceSize = targetTier;
    }
  }

  const patchBody = JSON.stringify({ replicationSpecs: [rs0] });

  // 3) PATCH cluster
  const patchResp = await context.http.patch({
    url: clusterUrl,
    headers: {
      Authorization: [`Bearer ${access_token}`],
      Accept: ["application/vnd.atlas.2024-10-23+json"],
      "Content-Type": ["application/json"],
    },
    body: patchBody,
  });

  const patchText = patchResp.body ? patchResp.body.text() : "";
  if (patchResp.statusCode < 200 || patchResp.statusCode >= 300) {
    throw new Error(`PATCH failed: ${patchResp.statusCode} ${patchText}`);
  }

  return { ok: true, statusCode: patchResp.statusCode, response: patchText };
};
```

### API Notes

- Atlas scaling is asynchronous.
- PATCH returns 200/202 while the cluster transitions.
- Avoid overlapping triggers.
- Allow sufficient time between scale-up and scale-down events.
- Ensure your service account has Project Owner or Project Cluster Manager role.

## Security Notes

- Never hardcode API keys in source code.
- Use least-privilege service account/token scopes.

## Demo Flow

1. Set `SCALE_UP_TIER` and `SCALE_DOWN_TIER` to your demo tiers.
2. Configure two Atlas Scheduled Triggers with CRON expressions.
3. Trigger scale-up for known peak window dates.
4. Trigger scale-down after the window.
5. Observe tier changes in Atlas UI and correlate with workload/latency metrics.
