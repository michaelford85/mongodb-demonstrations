# MongoDB Field-Level Encryption Demos

This repository contains two follow-along Python demos against a MongoDB Atlas cluster that already has the MongoDB sample datasets loaded:

- Client-Side Field Level Encryption (CSFLE) on `sample_mflix.users.email`
- Queryable Encryption (QE) on `sample_analytics.accounts.limit`

Both demos use a local KMS master key, a shared Atlas key vault, and Python scripts that let you apply encryption, query encrypted data, inspect decrypted values, and remove the demo encryption again.

## What Each Demo Shows

### CSFLE

The CSFLE demo encrypts `sample_mflix.users.email` with deterministic encryption:

- Algorithm: `AEAD_AES_256_CBC_HMAC_SHA_512-Deterministic`
- Why deterministic: the same plaintext produces the same ciphertext, which is what makes equality queries possible
- Tradeoff: deterministic encryption leaks equality patterns, so repeated values look repeated

Follow-along moment:

1. Run the CSFLE `apply` script.
2. Open `sample_mflix.users` in Atlas and inspect the `email` field. You should see `BinData(...)`.
3. Run the CSFLE `query` script with a plaintext email. The encrypted client will still match the document.
4. Run the same plaintext filter directly in Atlas without the encryption keys and it should return no match.

### Queryable Encryption

The QE demo recreates `sample_analytics.accounts` as an encrypted collection with a range-queryable `limit` field:

- Query type: `range`
- Why QE: range queries work even though the stored ciphertext is randomized
- Tradeoff: QE needs metadata collections and must be configured at collection creation time

Follow-along moment:

1. Run the QE `apply` script.
2. Open `sample_analytics.accounts` in Atlas and inspect the `limit` field. You should see encrypted binary data.
3. In Atlas, also note the hidden metadata collections prefixed with `enxcol.`.
4. Run the QE `query` script with `--min 5000 --max 10000`.
5. Notice that two documents with the same plaintext `limit` still have different ciphertext in Atlas, but both are returned by the range query through the encrypted client.

## CSFLE vs QE

Use CSFLE when:

- equality queries are enough
- you want direct control over deterministic vs randomized encryption
- you already use CSFLE and do not want QE metadata collections

Use QE when:

- you need searchable encrypted fields beyond deterministic equality
- you want randomized stored ciphertext while preserving supported queries
- you can create the collection with encrypted-field metadata up front

Operational difference:

- CSFLE can encrypt fields in an existing collection.
- QE must be enabled when the collection is created, so this demo backs up `sample_analytics.accounts`, drops it, recreates it as an encrypted collection, and reinserts the documents.

## Prerequisites

1. A MongoDB Atlas cluster with the sample datasets loaded.
2. Python 3.10+.
3. The Automatic Encryption Shared Library available to PyMongo.

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
python3 scripts/generate_local_master_key.py
```

Fill in `MONGODB_URI` in `.env`.

If PyMongo cannot find the Automatic Encryption Shared Library automatically, also set `CRYPT_SHARED_LIB_PATH` in `.env`.

## Environment Variables

`.env.example` contains the supported settings:

- `MONGODB_URI`: Atlas connection string
- `KEY_VAULT_NAMESPACE`: key vault namespace used for both demos
- `LOCAL_MASTER_KEY_PATH`: local 96-byte master key path
- `CRYPT_SHARED_LIB_PATH`: optional override for the Automatic Encryption Shared Library
- `CSFLE_KEY_ALT_NAME`: key alt name for the CSFLE DEK
- `QE_KEY_ALT_NAME`: key alt name for the QE DEK namespace
- `QE_RANGE_MIN`, `QE_RANGE_MAX`, `QE_RANGE_SPARSITY`: QE range configuration

## Running the CSFLE Demo

Apply encryption:

```bash
python3 scripts/csfle_demo.py apply
```

Query by plaintext email through the encrypted client:

```bash
python3 scripts/csfle_demo.py query --email "someone@example.com"
```

If you omit `--email`, the script pulls a value from the plaintext backup collection.

Inspect one decrypted field:

```bash
python3 scripts/csfle_demo.py decrypt
```

Remove the demo encryption and return `sample_mflix.users` to plaintext:

```bash
python3 scripts/csfle_demo.py remove
```

## Running the QE Demo

Apply encryption:

```bash
python3 scripts/qe_demo.py apply
```

Run the range query:

```bash
python3 scripts/qe_demo.py query --min 5000 --max 10000
```

Inspect one decrypted document:

```bash
python3 scripts/qe_demo.py decrypt
```

Remove the QE demo and restore `sample_analytics.accounts` to plaintext:

```bash
python3 scripts/qe_demo.py remove
```

## Notes

- Both demos create temporary backup collections before changing the sample collection.
- The CSFLE demo backup collection is `sample_mflix.users_csfle_backup`.
- The QE demo backup collection is `sample_analytics.accounts_qe_backup`.
- `remove` drops those backup collections after restoring plaintext data.
- These scripts are intentionally followable rather than highly optimized.
