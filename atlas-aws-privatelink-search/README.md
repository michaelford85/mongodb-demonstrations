# Atlas Full-Text Search over AWS PrivateLink (No Public Internet)

This demo shows how to run a **MongoDB Atlas Search (full-text)** query from an **Ubuntu 24.04 EC2 instance** over **AWS PrivateLink**, so application traffic to Atlas stays on AWS’s private network and **does not traverse the public internet**.

You’ll also verify the network path using **VPC Flow Logs**.

---

## What you’ll build

- An AWS VPC with private subnets
- An Ubuntu 24.04 EC2 instance (in a private subnet)
- AWS **Interface VPC Endpoints** for Atlas **PrivateLink**
- App code (Python + `pymongo`) and `mongosh` connectivity
- An Atlas Search query (full-text) executed over the PrivateLink connection
- Verification using **VPC Flow Logs** (and optional CloudWatch Logs Insights / Athena)

---

## Architecture (high level)

1. Your EC2 instance sits in a **private subnet** (no public IP).
2. Your VPC has **Interface Endpoints** (ENIs with private IPs) for Atlas PrivateLink.
3. Your app connects to Atlas using the **PrivateLink connection string** (or Private DNS enabled path).
4. VPC Flow Logs show traffic from EC2 → endpoint ENI private IPs over 443, with no egress via IGW/NAT for database traffic.

---

## Repository layout (suggested)

```
atlas-privatelink-search/
  README.md
  terraform/
    main.tf
    variables.tf
    outputs.tf
    versions.tf
  server/
    bootstrap.sh
  app/
    requirements.txt
    search_demo.py
    .env.example
```

> Feel free to adapt this to your `mongodb-demonstrations` repo conventions.

---

## Prerequisites

### Accounts / access
- AWS account with permissions to create:
  - VPC/Subnets/Security Groups
  - EC2
  - VPC Flow Logs
  - (Optional) CloudWatch Logs / S3 / Athena
- MongoDB Atlas project + cluster:
  - Cluster **must already exist** and include **Atlas Search** (Search Nodes / Search enabled).
  - You must have permission to create **PrivateLink** connections in Atlas.

### Local tools
- `terraform` (recommended)
- `aws` CLI configured
- `mongosh` (optional locally; you’ll also install it on the server)

---

## Step 0 — Identify your Atlas cluster requirements

Before touching AWS, capture these details:

- Atlas **Project ID**
- Atlas **Cluster name**
- Atlas **AWS region** (must match the region you deploy your VPC endpoints into)
- Atlas Search index name + collection being searched
- An Atlas database user/password (or X.509 / AWS IAM auth if you prefer)

---

## Step 1 — Deploy AWS VPC + Ubuntu 24.04 server (Terraform)

> The goal is an EC2 instance in a **private subnet**. You can still reach it via:
> - AWS SSM Session Manager (recommended), OR
> - a temporary bastion in a public subnet, OR
> - your existing VPN / Direct Connect

### Terraform: VPC + EC2 baseline

In `terraform/` create resources for:

- VPC (e.g., `10.0.0.0/16`)
- 2 private subnets (e.g., `10.0.1.0/24`, `10.0.2.0/24`)
- Route tables for private subnets
- Security group for EC2:
  - Allow outbound **TCP 443** (to reach PrivateLink endpoints)
  - Allow outbound **TCP 27017** if your connection string uses 27017 (most PrivateLink strings use 27017 over TLS)
- EC2 instance:
  - Ubuntu 24.04 AMI (HVM)
  - No public IP
  - Instance profile if using SSM
- (Recommended) VPC endpoints for SSM:
  - `com.amazonaws.<region>.ssm`
  - `com.amazonaws.<region>.ssmmessages`
  - `com.amazonaws.<region>.ec2messages`

Deploy:

```bash
cd terraform
terraform init
terraform apply
```

Capture outputs:
- VPC ID
- Private subnet IDs
- EC2 instance ID + private IP

---

## Step 2 — Install Ubuntu packages + pip packages on the server

SSH/SSM into the Ubuntu instance, then:

### Ubuntu packages (`apt`)

```bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl gnupg lsb-release jq unzip \
  python3 python3-venv python3-pip \
  tcpdump net-tools dnsutils
```

### Install `mongosh` (server-side)

MongoDB provides an official `mongosh` install path via packages, but if you prefer a simple approach for demos, download the Linux tarball:

```bash
mkdir -p ~/tools && cd ~/tools
# Replace URL with a current mongosh Linux x64 release if needed
# (You can also install via official MongoDB repos)
```

> If you already have a preferred `mongosh` installation method in your repo, use that here.

### Python virtual environment + pip packages

```bash
mkdir -p ~/atlas-privatelink-search && cd ~/atlas-privatelink-search
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install pymongo python-dotenv dnspython
```

---

## Step 3 — Configure Atlas PrivateLink

### 3A — Create the PrivateLink connection in Atlas

In Atlas:
1. Go to **Network Access → Private Endpoint** (or **PrivateLink** depending on UI).
2. Choose **AWS**.
3. Create a new private endpoint for the **same AWS region** as your VPC.
4. Atlas will display:
   - **Service name** (AWS endpoint service name)
   - A list of **private endpoint DNS names** (used for connection strings)
   - Instructions to create **Interface Endpoints** in your VPC

Keep this page open—you will copy/paste values.

### 3B — Create Interface VPC Endpoints in AWS

In AWS VPC console (or Terraform), create **Interface Endpoints** to the Atlas service name from step 3A:

- VPC: the one you created
- Subnets: **private subnets** where your EC2 instance resides
- Security Group on endpoints:
  - Inbound: allow TCP 443 and/or 27017 **from the EC2 security group**
  - Outbound: allow all (or at least return traffic)

After creation, the endpoints will have **ENIs** with **private IPs**.

### 3C — Approve the endpoint connection in Atlas

Back in Atlas, you must **approve** the pending endpoint connection request.

Once approved, Atlas will provide a **PrivateLink connection string** for your cluster.

---

## Step 4 — Confirm DNS + connectivity from the EC2 instance

### 4A — DNS checks

On the EC2 instance:

```bash
# Example: replace with the PrivateLink hostname Atlas provides
nslookup <your-privatelink-hostname>
```

You want to see private IPs that correspond to the endpoint ENIs.

### 4B — Network path sanity checks

```bash
# (Optional) See routes; ensure DB traffic isn't going to a NAT/IGW route
ip route

# Quick TCP connectivity (replace hostname/port)
nc -vz <your-privatelink-hostname> 27017
```

> Depending on your Atlas PrivateLink setup, you may connect on 27017 or 443. Use the port Atlas provides in the connection string.

---

## Step 5 — Run a full-text Atlas Search query over PrivateLink

### 5A — Set environment variables

Create `.env`:

```bash
cat > .env <<'EOF'
MONGODB_URI="mongodb+srv://<user>:<pass>@<your-privatelink-connection-string>/?retryWrites=true&w=majority"
DB_NAME="sample_mflix"
COLLECTION_NAME="movies"
SEARCH_INDEX="default"
QUERY="star wars"
EOF
```

> Use the **PrivateLink** connection string Atlas provides (not the public one).

### 5B — Example Python app: `app/search_demo.py`

```python
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.environ["MONGODB_URI"]
db_name = os.environ["DB_NAME"]
coll_name = os.environ["COLLECTION_NAME"]
index_name = os.environ["SEARCH_INDEX"]
q = os.environ.get("QUERY", "test")

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
coll = client[db_name][coll_name]

pipeline = [
    {
        "$search": {
            "index": index_name,
            "text": {
                "query": q,
                "path": ["title", "plot"]
            }
        }
    },
    {"$limit": 5},
    {"$project": {"title": 1, "year": 1, "score": {"$meta": "searchScore"}}},
]

results = list(coll.aggregate(pipeline))
for doc in results:
    print(doc)
```

Run it:

```bash
cd ~/atlas-privatelink-search
source .venv/bin/activate
python app/search_demo.py
```

If it returns results, you’ve successfully used **Atlas Search** over **PrivateLink**.

---

## Step 6 — Verify traffic stays off the public internet (VPC Flow Logs)

VPC Flow Logs won’t prove “no internet” by itself, but it *does* let you confirm:
- Your EC2 instance is talking to **private IPs** (the endpoint ENIs)
- The traffic stays within the VPC / AWS private ranges
- There’s no evidence of database connections going to public IP destinations

### 6A — Enable VPC Flow Logs

Enable Flow Logs at either the **VPC** or (preferred for clarity) the **EC2 ENI** level:

- Destination:
  - **CloudWatch Logs** (easy for demos), OR
  - **S3** (best for Athena queries / long retention)
- Filter: `ALL` (or at least `ACCEPT`)
- Log format: include at minimum
  - `srcaddr`, `dstaddr`, `srcport`, `dstport`, `protocol`, `action`, `bytes`, `packets`, `interface-id`

### 6B — Generate traffic

Run your Python script a few times and/or run `mongosh` commands.

### 6C — Identify your Endpoint ENIs + private IPs

In AWS:
1. VPC → Endpoints → select the Atlas endpoint
2. Note the **network interface IDs** and their **private IP addresses**

You should now have:
- EC2 ENI / private IP (source)
- Endpoint ENI private IP(s) (destination)

### 6D — Query Flow Logs (CloudWatch Logs Insights example)

If you sent Flow Logs to CloudWatch Logs, use Logs Insights:

Example query (edit field names if your log format differs):

```sql
fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, action, bytes
| filter srcAddr = "10.0.1.123"
| filter (dstPort = 443 or dstPort = 27017)
| sort @timestamp desc
| limit 50
```

What you want to see:
- `dstAddr` values are **private IPs** belonging to the **Interface Endpoint ENIs**
- Traffic is `ACCEPT`
- Ports align with your Atlas PrivateLink connection behavior (443 and/or 27017)

### 6E — Extra “no-internet” confidence checks

To increase confidence that your DB traffic isn’t using the internet:

- Ensure the EC2 instance:
  - Has **no public IP**
  - Has no route to an Internet Gateway
- Ensure your private subnet route table:
  - Does **not** route `0.0.0.0/0` to an IGW
  - (If you have a NAT for patching, that’s okay — you’re proving DB traffic goes to endpoint ENIs, not NAT.)
- Optionally, capture packets on the EC2 instance:

```bash
sudo tcpdump -n host <endpoint_private_ip> and '(port 443 or port 27017)'
```

> Packet capture confirms the destination IP/port, but not “public vs private internet.” The key proof is: endpoint ENI private IPs + VPC-internal flows.

---

## Troubleshooting

### “Could not find host” / DNS issues
- Verify you used the **PrivateLink** hostname Atlas provided.
- Check whether **Private DNS** is enabled for the interface endpoint (and that your VPC DNS settings are enabled).

### Connection timeouts
- Confirm security groups:
  - EC2 outbound allows 443/27017
  - Endpoint SG inbound allows from EC2 SG
- Confirm endpoints are in the **same subnets/AZs** you expect
- Confirm the endpoint connection is **approved** in Atlas

### Search query fails
- Confirm the cluster has Search enabled and you created a Search index
- Confirm the `SEARCH_INDEX` name matches
- Confirm the `path` fields exist in your documents

---

## Cleanup

```bash
cd terraform
terraform destroy
```

Also delete:
- VPC Flow Logs (if created manually)
- CloudWatch log groups / S3 buckets / Athena tables (if applicable)

---

## Notes and security reminders

- Never commit `.env` or credentials.
- Prefer AWS SSM over SSH where possible.
- PrivateLink keeps traffic on AWS’s network, but you still need proper TLS, auth, and least-privilege IAM.

---

## Next enhancements (optional)
- Add Terraform for the **Interface Endpoints** + Flow Logs setup
- Provide an Athena query example for Flow Logs stored in S3
- Add a “public vs PrivateLink” comparison by running the same query from a public subnet and contrasting `dstAddr` values
