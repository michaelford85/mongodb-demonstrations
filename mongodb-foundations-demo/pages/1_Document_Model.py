"""Section ①: the document model and how it maps to relational thinking."""

import streamlit as st

from lib.mongo_client import ACCOUNTS, COLLECTIONS, CUSTOMERS, TRANSACTIONS
from lib.schema import (REJECTED_EXAMPLES, VALIDATORS, try_rejected_example,
                        validator_info)
from lib.ui import (connection_guard, cue, db, mql, page_header, page_setup,
                    presenter_mode, prose, seed_guard, sidebar_reset,
                    synthetic_note, table, takeaway)

page_setup("Document model", icon="①")
presenter_mode()
connection_guard()
sidebar_reset()
seed_guard()
database = db()

page_header("①", "Document model & data modeling",
            "One customer, stored the way the application reads it.")

MAPPING = [
    {"Relational": "table", "MongoDB": "collection",
     "In this demo": "`customers`, `accounts`, `transactions`"},
    {"Relational": "row", "MongoDB": "document",
     "In this demo": "one customer profile"},
    {"Relational": "column", "MongoDB": "field",
     "In this demo": "`segment`, `joined_on`"},
    {"Relational": "related data in a child table",
     "MongoDB": "nested subdocument / array",
     "In this demo": "`address`, `contact`, `preferences`, `recent_alerts`"},
    {"Relational": "foreign key", "MongoDB": "identifier stored in a document",
     "In this demo": "`accounts.customer_id` → `customers.customer_id`"},
]

# Plain-language summary of each collection's validator, shown beside the live
# level/action the server reports.
RULE_SUMMARY = {
    CUSTOMERS: "`customer_id`, `name`, `segment`, `address`, `contact` required · "
               "`segment` and `preferences.contact_channel` restricted to a list · "
               "`address.state` must be two capitals · `recent_alerts` capped at 3",
    ACCOUNTS: "`account_number`, `customer_id`, `account_type`, `status`, "
              "`currency`, `balance` required · `balance` numeric and ≥ 0 · "
              "`account_type`, `status`, `currency` restricted to a list",
    TRANSACTIONS: "`txn_id`, `account_number`, `category`, `direction`, "
                  "`amount`, `posted_at` required · `amount` > 0 · "
                  "`direction` debit or credit · `posted_at` must be a date",
}

customer_ids = sorted(database[CUSTOMERS].distinct("customer_id"))
selected = st.selectbox("Customer", customer_ids)
document = database[CUSTOMERS].find_one({"customer_id": selected})

left, right = st.columns([3, 2])

with left:
    st.markdown("#### The document")
    mql(document, language="json")

with right:
    st.markdown("#### Relational → document")
    table(MAPPING)

    st.markdown("#### Embedded, because it is read with the customer")
    embedded = {
        "contact": document.get("contact"),
        "preferences": document.get("preferences"),
        "recent_alerts": document.get("recent_alerts"),
    }
    mql(embedded, language="json")
    st.caption("`recent_alerts` is deliberately bounded — at most three "
               "entries. Embedding an unbounded history would grow the "
               "document without limit.")

    st.markdown("#### Referenced, because its lifecycle is independent")
    account_rows = list(database[ACCOUNTS].find(
        {"customer_id": selected},
        {"_id": 0, "account_number": 1, "account_type": 1, "status": 1,
         "balance": 1}))
    table(account_rows, "This customer has no accounts in the demo data.")
    st.caption("Accounts open, close, and change balance on their own "
               "schedule, and are queried on their own. They live in "
               "`{}` and carry `customer_id`.".format(ACCOUNTS))

cue("Model from access patterns: what is read and written together?")

st.markdown("---")
st.markdown("#### Flexible schema, still governed: `$jsonSchema` validation")
st.caption("Every collection in this demo is created with a validator, so the "
           "server — not the application — enforces these rules.")

live = {name: validator_info(database, name) for name in COLLECTIONS}
table([{"collection": name,
        "validator active": bool(live[name].get("validator")),
        "level": live[name].get("validationLevel", "—"),
        "action": live[name].get("validationAction", "—"),
        "rules": RULE_SUMMARY[name]} for name in COLLECTIONS])

rules_left, rules_right = st.columns([3, 2])

with rules_left:
    which = st.selectbox("Show the validator for", COLLECTIONS,
                         key="validator_collection")
    mql(VALIDATORS[which]["validator"], language="json")

with rules_right:
    st.markdown("##### Watch the server reject a write")
    st.caption("Breaks one rule on purpose: {}"
               .format(REJECTED_EXAMPLES[which]["rule"]))
    mql(REJECTED_EXAMPLES[which]["document"], language="json")
    if st.button("Attempt the invalid insert", key="attempt_invalid"):
        outcome = try_rejected_example(database, which)
        if outcome["rejected"]:
            st.success("Rejected by the server · error code {}"
                       .format(outcome["code"]))
            with st.expander("Server response"):
                st.write(outcome["error"])
                if outcome["details"]:
                    mql(outcome["details"], language="json")
        else:
            st.warning(outcome["error"])
    st.caption("The document is invalid by construction, so nothing is written.")

cue("Schema-less does not mean rule-less. Validation is a per-collection choice.")

prose(
    "**Why this split, in plain language.** Contact details and preferences are "
    "read every single time the customer profile is read, they are small, and "
    "they are bounded — so storing them inside the customer document removes a "
    "join from the common path. Accounts are different: they are updated by "
    "processes that do not care about the profile, they are listed and "
    "aggregated on their own, and a balance changes far more often than a "
    "mailing address. A reference keeps those write paths independent.\n\n"
    "**Embedding is not a default.** It is a choice that trades join-free reads "
    "against document growth and write amplification. The relational instinct "
    "to normalise everything and the document instinct to embed everything are "
    "both wrong as blanket rules. The question is the same in either model: "
    "which pieces of data are used together, and how often does each piece "
    "change?\n\n"
    "**Note on money.** Balances here are stored as doubles for readability. A "
    "production ledger would use `Decimal128` or integer minor units.\n\n"
    "**Schema validation, for the DBA.** MongoDB does not require a schema, but "
    "it will enforce one. A `$jsonSchema` validator is attached to the "
    "collection and applied by the server on every insert and update, which "
    "covers the same ground as `NOT NULL`, a type declaration, a `CHECK` "
    "constraint, and a small domain table. Two dials control how strict it is. "
    "`validationLevel` is `strict` (validate every write) or `moderate` "
    "(documents that already violate the rules are exempt when they are "
    "updated — the practical setting while a legacy collection is being "
    "cleaned up). `validationAction` is `error` (reject the write) or `warn` "
    "(accept it and log the violation, which is how you measure a rule before "
    "you enforce it). `transactions` is deliberately `moderate` here so both "
    "levels are visible.\n\n"
    "**What it is not.** The validator does not describe every field — fields "
    "it does not mention are still allowed, so the model can be extended "
    "without a migration. Rules are added or relaxed with `collMod`, which is "
    "a metadata change: no table rewrite and no downtime.")

takeaway("A document is the unit of both storage and access. Embed what is read "
         "together and bounded; reference what has an independent lifecycle.")

synthetic_note()
