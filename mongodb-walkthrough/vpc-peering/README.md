# VPC Peering

No script is required here — VPC peering is an infrastructure configuration that happens once at the network level. This walkthrough covers what it is, why it matters, and what both sides need to configure.

---

## What VPC peering does

By default, Atlas clusters are reachable over the public internet (with IP allowlisting). VPC peering creates a **private network route** between your cloud provider VPC and the Atlas-managed VPC, so traffic never leaves the cloud provider's backbone.

```
Your Application VPC                  Atlas VPC (managed)
┌──────────────────────┐              ┌──────────────────────┐
│  App servers         │◄────peer────►│  MongoDB nodes       │
│  10.0.0.0/16         │   (private)  │  192.168.248.0/21    │
└──────────────────────┘              └──────────────────────┘
         No public internet traversal
```

---

## Prerequisites on the Atlas side

Each Atlas project gets one Atlas-managed VPC per cloud provider per region. You cannot choose the CIDR — Atlas assigns it. Before initiating peering you need:

- The Atlas VPC CIDR for your region (visible in Atlas UI → Network Access → Peering)
- Confirm it does not overlap with your application VPC CIDR

> **CIDR overlap is the most common failure point.** If `10.0.0.0/16` is used by both sides, peering will be rejected. Plan CIDRs before provisioning.

---

## What to collect from the customer

### AWS

| Field | Where to find it |
|---|---|
| AWS Account ID | AWS Console → top-right account menu |
| Application VPC ID | VPC Console → Your VPCs |
| Application VPC CIDR | VPC Console → Your VPCs → CIDR column |
| AWS Region | Must match the Atlas cluster region |

### Azure

| Field | Where to find it |
|---|---|
| Subscription ID | Azure Portal → Subscriptions |
| Directory (Tenant) ID | Azure AD → Properties |
| VNet name and resource group | Virtual Networks |
| VNet CIDR | Virtual Networks → Address space |

### GCP

| Field | Where to find it |
|---|---|
| GCP project ID | GCP Console → project selector |
| VPC network name | VPC Networks |
| GCP region | Must match Atlas cluster region |

---

## Initiating from Atlas

1. Atlas UI → **Network Access** → **Peering** tab → **Add Peering Connection**
2. Select your cloud provider
3. Enter the fields collected above
4. Atlas creates a peering request — you will see a **Pending Acceptance** status

### AWS: accept in the AWS Console

```
VPC Console → Peering Connections → select the pending request → Actions → Accept
```

Then add a route to your route table pointing the Atlas CIDR at the peering connection.

### Azure / GCP

Both sides initiate simultaneously. Atlas handles the GCP side; for Azure you also need to approve the peering in the Azure portal.

---

## After peering is active

- Remove or tighten your Atlas IP Access List — you can restrict it to the peered VPC CIDR only
- Update your connection string if needed (the hostname stays the same; peering just changes the routing path)
- Test with a `ping` or `mongosh` from within the VPC to confirm private routing

---

## Key talking points

- Peering is per-region — a multi-region cluster needs a peering connection in each region where your application runs
- Atlas Private Endpoints (AWS PrivateLink / Azure Private Link) are an alternative that avoids CIDR overlap issues entirely and is preferred for stricter network segmentation requirements
- Peering does not replace authentication — the cluster still requires credentials and TLS
