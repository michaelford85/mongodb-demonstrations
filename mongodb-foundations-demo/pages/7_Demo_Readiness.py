"""Demo readiness: verify the environment before the session starts."""

import streamlit as st
from pymongo.errors import PyMongoError

from lib.mongo_client import DB_NAME, MissingUriError, counts
from lib.readiness import run_all
from lib.schema import VALIDATORS
from lib.seed import REQUIRED_INDEXES, seed
from lib.ui import (page_header, page_setup, presenter_mode, prose,
                    sidebar_reset, synthetic_note, table)

page_setup("Demo readiness", icon="🩺")
presenter_mode()
sidebar_reset()

page_header("🩺", "Demo readiness",
            "Seven checks. Run this before the audience arrives.")

if st.button("🔄 Re-run all checks", type="primary"):
    st.session_state.pop("readiness", None)

if "readiness" not in st.session_state:
    st.session_state["readiness"] = run_all()

rows = st.session_state["readiness"]
passed = sum(1 for row in rows if row["ok"])
if passed == len(rows):
    st.success("All {} checks passed. The session is ready to run."
               .format(len(rows)))
else:
    st.warning("{} of {} checks passed. See the fixes below."
               .format(passed, len(rows)))

table([{"check": row["name"], "status": "PASS" if row["ok"] else "FAIL",
        "detail": row["detail"], "fix": row["fix"]} for row in rows])

st.markdown("---")
st.markdown("#### Seed the demo namespace")
st.caption("Nothing is written when the app starts. Seeding is always an "
           "explicit, confirmed action, and it only touches `{}`."
           .format(DB_NAME))

if st.button("🌱 Seed demo data"):
    st.session_state["seed_pending"] = True

if st.session_state.get("seed_pending"):
    st.warning("This drops and rebuilds the three collections in `{}` from the "
               "deterministic seed — applying each collection's schema "
               "validator — then creates the {} demo indexes."
               .format(DB_NAME, sum(len(s) for s in REQUIRED_INDEXES.values())))
    confirm, cancel = st.columns(2)
    if confirm.button("Confirm seed", type="primary"):
        st.session_state["seed_pending"] = False
        try:
            result = seed()
            st.success("Seeded · {}".format(
                " · ".join("{}={}".format(k, v) for k, v in result.items())))
            st.session_state.pop("readiness", None)
        except (MissingUriError, PyMongoError) as exc:
            st.error("Seed failed: {}".format(exc))
    if cancel.button("Cancel"):
        st.session_state["seed_pending"] = False
        st.rerun()

st.markdown("#### Current contents")
try:
    table([{"collection": name, "documents": total}
           for name, total in counts().items()])
except (MissingUriError, PyMongoError) as exc:
    st.info("Cannot read the demo database yet: {}".format(exc))

st.markdown("#### Indexes this demo creates")
table([{"collection": coll, "index": name,
        "keys": ", ".join("{}: {}".format(f, d) for f, d in keys),
        "unique": bool(opts.get("unique", False))}
       for coll, specs in REQUIRED_INDEXES.items()
       for name, (keys, opts) in specs.items()])

st.markdown("#### Schema validators this demo applies")
table([{"collection": name, "level": opts["validationLevel"],
        "action": opts["validationAction"],
        "required fields": ", ".join(
            opts["validator"]["$jsonSchema"].get("required", []))}
       for name, opts in VALIDATORS.items()])
st.caption("Shown in full, with a live rejected write, in section ①.")

prose(
    "**What each check means.** `MONGODB_URI available` confirms the variable is "
    "set — the value is never displayed or logged. `Connection` proves the "
    "deployment is reachable within the timeout. `Database permissions` inspects "
    "the connected user's roles and privileges to confirm it can write to `{}`. "
    "`Seed data` and `Demo indexes` confirm the demo namespace is populated and "
    "indexed. `Schema validators` confirms each collection still carries its "
    "`$jsonSchema` rules. `Transaction demo` confirms the deployment reports a "
    "replica set and that both dedicated demo accounts exist.\n\n"
    "**If a check fails.** Each row carries the exact fix. The most common cause "
    "is that this machine's IP address is not on the deployment's access list, "
    "which surfaces as a connection timeout rather than an authentication "
    "error.".format(DB_NAME))

st.markdown("---")
synthetic_note()
st.caption("The command-line equivalent of this page: `python3 scripts/status.py`")
