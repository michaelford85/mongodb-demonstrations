# MongoDB Atlas Walkthrough

This directory contains a set of focused, live-runnable demonstrations for MongoDB Atlas capabilities. Each subfolder is self-contained and covers one topic.

All demos assume a running Atlas cluster loaded with the [MongoDB sample datasets](https://www.mongodb.com/docs/atlas/sample-data/). Use the [`../atlas-cluster-provisioning`](../atlas-cluster-provisioning) scripts to spin one up and tear it down.

---

## Subfolders

| Folder | What it shows |
|---|---|
| [`online-archive/`](online-archive/) | Configure hot/cold data tiering with Atlas Online Archive; timed queries against live vs. archived data |
| [`multi-region/`](multi-region/) | How Atlas handles geographic distribution, region failover, and read locality |
| [`multi-tenancy/`](multi-tenancy/) | Database-per-tenant isolation pattern demonstrated live against the cluster |
| [`vpc-peering/`](vpc-peering/) | How Atlas VPC peering works and what both sides need to configure |
| [`connection-pooling/`](connection-pooling/) | Cost of new connections vs. pool reuse, benchmarked with real queries |
| [`data-modeling/`](data-modeling/) | Relational-to-document model translation with side-by-side schema comparisons |

---

## Prerequisites

- Python 3.11+
- A MongoDB Atlas cluster with sample datasets loaded
  (Atlas UI → your cluster → `...` → *Load Sample Dataset*)
- Each subfolder has its own `.env.example` and `requirements.txt`
