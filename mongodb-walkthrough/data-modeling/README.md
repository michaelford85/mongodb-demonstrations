# Data Modeling: Relational to Document

This walkthrough shows how a normalized relational schema maps to a MongoDB document model. No script is needed — the schema comparisons below are the demo.

---

## The relational baseline

A typical normalized schema separates data into linked tables to avoid duplication:

```
customers          orders              order_items         products
──────────         ──────────          ──────────────      ──────────
id (PK)            id (PK)             id (PK)             id (PK)
name               customer_id (FK)    order_id (FK)       name
email              order_date          product_id (FK)     category
phone              status              quantity            unit_price
                   shipping_addr_id    unit_price          weight_kg

addresses
──────────
id (PK)
customer_id (FK)
line1, line2
city, state
postal_code
country
```

Fetching a complete order requires **4–5 joins**. Every join is a round trip or a query planner decision.

---

## The document model equivalent

MongoDB stores the complete, queryable unit as a single document. A document maps to how the application actually reads and writes the data — not how a storage theorist would normalize it.

```json
{
  "_id": "ord_8472",
  "status": "shipped",
  "order_date": { "$date": "2024-03-15T09:22:00Z" },

  "customer": {
    "id": "cust_1290",
    "name": "Acme Corp",
    "email": "orders@acme.example",
    "shipping_address": {
      "line1": "100 Main St",
      "city": "Springfield",
      "postal_code": "62701",
      "country": "US"
    }
  },

  "items": [
    {
      "product_id": "prod_441",
      "name": "Widget A",
      "category": "hardware",
      "quantity": 2,
      "unit_price": 29.99
    },
    {
      "product_id": "prod_882",
      "name": "Component B",
      "category": "hardware",
      "quantity": 1,
      "unit_price": 149.00
    }
  ],

  "totals": {
    "subtotal": 208.98,
    "tax": 16.72,
    "total": 225.70
  }
}
```

One read. No joins.

---

## Key design decisions

### Embed vs. reference

| Embed when… | Reference when… |
|---|---|
| Data is always read together | Data is read independently at different times |
| The child has no life outside the parent | The child is shared across many parents |
| The subdocument is bounded in size | The subdocument grows unboundedly (e.g. append-only logs) |

In the order example above: `items` are always read with the order → **embed**. `products` are also managed independently (price changes, catalog updates) → keep a **snapshot** of the price at order time in the embedded item, and a separate `products` collection for catalog management.

### Arrays are first-class

MongoDB indexes array fields natively. Finding all orders containing a specific product:

```javascript
db.orders.find({ "items.product_id": "prod_441" })
```

No join table. No pivot. One index on `items.product_id` covers this query.

### Flexible schema is intentional

Fields can vary per document. A `digital_order` document might omit `shipping_address` entirely. A `subscription_order` might add a `billing_cycle` field. Neither requires a schema migration — both coexist in the same collection.

---

## Mapping your existing schema

The general process for migrating from a relational model:

1. **Identify the primary read pattern** — what does the application fetch most often, and what does it fetch together?
2. **Group by access pattern** — data accessed together should live together (embed)
3. **Preserve references for shared entities** — things with independent lifecycles stay separate
4. **Snapshot point-in-time values** — copy prices, names, addresses into the transaction document at write time so historical records stay accurate even if the source changes

MongoDB's [Relational Migrator](https://www.mongodb.com/products/tools/relational-migrator) tool automates schema analysis and can generate a suggested document model from an existing relational schema, including DDL and migration scripts.

---

## The `sample_mflix` dataset as a live example

The `movies` collection in `sample_mflix` is itself a good document model example. A relational equivalent would need separate tables for movies, genres, cast members, directors, writers, and awards. In `sample_mflix`:

```javascript
db.movies.findOne({ title: "The Matrix" })
// Returns genres, cast, directors, writers, awards, imdb rating —
// all in one document, one read, zero joins.
```

```javascript
// Find all sci-fi movies with an IMDB rating above 8 — one query, one index
db.movies.find(
  { genres: "Sci-Fi", "imdb.rating": { $gt: 8 } },
  { title: 1, year: 1, "imdb.rating": 1, _id: 0 }
).sort({ "imdb.rating": -1 })
```
