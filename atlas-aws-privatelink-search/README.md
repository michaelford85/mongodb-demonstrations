# MongoDB Atlas + AWS PrivateLink (Search Traffic Validation)

## Purpose

This demonstration shows how to **prove that MongoDB Atlas Search traffic is not traversing the public internet** by:

- Running search queries from an EC2 instance in a **private subnet**
- Connecting to Atlas via **AWS PrivateLink**
- Validating DNS resolution and routing behavior at the **OS and network level**

> ⚠️ **Important:** This demo intentionally **does not rely on VPC Flow Logs**. Flow Logs can be misleading when validating PrivateLink traffic because they may surface public IPs used by AWS-managed infrastructure even when traffic stays on the AWS backbone.

Instead, this repo focuses on **deterministic validation methods** that are easier to explain to customers and auditors.

---

## What This Demo Proves

By following this guide, you will demonstrate:

- The application host has **no public IP**
- DNS for the Atlas PrivateLink endpoint resolves to **private RFC1918 IPs**
- Database and Search traffic **never traverses an Internet Gateway**
- All Atlas communication occurs over **AWS private infrastructure**

This aligns with common enterprise security requirements:

- No public ingress to database infrastructure
- No internet routing for sensitive data paths
- Explicit separation of admin access vs application traffic

---

## Architecture Overview

```
Home Laptop
    │
    │ SSH
    ▼
Bastion Host (Public Subnet)
    │
    │ SSH (private IP only)
    ▼
Application EC2 (Private Subnet)
    │
    │ TLS over AWS backbone
    ▼
AWS PrivateLink Endpoint
    │
    ▼
MongoDB Atlas Cluster
  • Dedicated Search Nodes
  • Private Endpoint Only
```

---

## Prerequisites

### AWS

- One VPC
- One **public subnet** (for bastion host)
- One **private subnet** (for application host)
- Internet Gateway (attached to VPC)
- NAT Gateway (for outbound-only access from private subnet)

### EC2

- Bastion host (Ubuntu 24.04)
  - Public IP
  - SSH restricted to your source IP

- Application host (Ubuntu 24.04)
  - **No public IP**
  - Route table includes:
    - `0.0.0.0/0 → NAT Gateway`
    - VPC CIDR → `local`

### MongoDB Atlas

- Dedicated cluster
- **Dedicated Search Nodes enabled**
- AWS PrivateLink endpoint configured and **Available**
- Private DNS **disabled** (we rely on Atlas-provided DNS)

---

## Repository Contents

```
.
├── README.md
├── search_demo.py
├── .env.example
└── requirements.txt
```

- `search_demo.py` – Runs a simple Atlas Search query
- `.env.example` – Environment variable template (safe dummy values)
- `requirements.txt` – Python dependencies

---

## Step 1: Launch the Application EC2 Instance

Launch an Ubuntu 24.04 EC2 instance in the **private subnet**:

- ❌ No public IP
- ✅ Security group allows:
  - SSH **only from bastion host SG**
  - Outbound HTTPS (443)

Confirm:

```bash
ip addr show
curl ifconfig.me   # should FAIL or return nothing
```

---

## Step 2: Access the Instance via Bastion Host

From your laptop:

```bash
ssh ubuntu@<BASTION_PUBLIC_IP>
```

From the bastion:

```bash
ssh ubuntu@<PRIVATE_EC2_PRIVATE_IP>
```

---

## Step 3: Install Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv dnsutils

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 4: Configure Environment Variables

Copy the example file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
MONGODB_URI="mongodb+srv://<username>:<password>@private-link-cluster-pl-0.xxxxx.mongodb.net/?appName=privatelink-search-demo"
DB_NAME=sample_mflix
COLLECTION_NAME=movies
SEARCH_INDEX=movies_fts_index
QUERY=star wars
```

> Note: TLS is **implicitly enabled** by the `mongodb+srv://` scheme.

---

## Step 5: Prove Private DNS Resolution

Run **from the private EC2 instance**:

```bash
dig +short private-link-cluster-pl-0.xxxxx.mongodb.net
```

Expected result:

- One or more **RFC1918 addresses** (e.g. `172.31.x.x`)
- ❌ No public IPs

Optional:

```bash
nslookup private-link-cluster-pl-0.xxxxx.mongodb.net
```

---

## Step 6: Run the Search Demo

```bash
python search_demo.py
```

You should see valid search results returned from Atlas.

This confirms:

- Application → Search traffic is functional
- TLS connectivity is established
- Traffic is routed through PrivateLink

---

## Step 7: Prove No Internet Path Exists

From the private EC2 instance:

```bash
ip route
```

Expected:

- Default route → NAT Gateway
- No route pointing directly to an Internet Gateway

Optional sanity check:

```bash
ip route get <PUBLIC_IP>
```

You should see the path traverse the **private interface**, not a public one.

---

## Why We Do NOT Use VPC Flow Logs Here

While VPC Flow Logs are valuable operationally, they are **not ideal for proving PrivateLink behavior to customers**:

- AWS-managed services may surface public IPs internally
- Search nodes may use shared AWS infrastructure
- Flow Logs do not represent routing domains

This demo uses **deterministic signals instead**:

- DNS resolution
- Routing tables
- Network isolation
- Absence of public ingress

These are easier to reason about and align better with security reviews.

---

## Key Takeaway for Prospects

> **All database and search traffic remains on AWS private infrastructure and is never exposed to the public internet. Administrative access is strictly separated from application traffic.**

---

## Next Steps (Optional)

- Add VPC Reachability Analyzer validation
- Add packet capture example (`tcpdump` showing private IPs)
- Extend demo to Kubernetes (EKS + PrivateLink)

---

Questions? This repo is intentionally designed to be **auditor-friendly, security-team-readable, and reproducible**.

