"""Northstar Payments — Command Center.

A GUI-first control center for a fictional multi-region card authorization
platform, backed entirely by MongoDB Atlas. Run the seed script first, then:

    streamlit run app.py

This is an illustrative field demo, not a performance or compliance harness.
"""

import time

import pandas as pd
import streamlit as st

from lib.atlas_client import (REGIONS, db_name, get_db, is_empty,
                              supports_change_streams)
from lib.sample_data import build_accounts, build_instruments, build_merchants
from lib.simulator import generate_event, take_snapshot
from lib import queries

st.set_page_config(page_title="Northstar Payments — Command Center",
                   page_icon="💳", layout="wide")

STATUS_STYLE = {
    "approved": ("✅", "#059669"),
    "declined": ("⛔", "#dc2626"),
    "pending": ("⏳", "#d97706"),
}
PAYMENT_LABELS = {
    "card_present": "💳 Card present",
    "wallet_token": "📱 Tokenized wallet",
    "installment": "🧾 Installment / split tender",
}


def status_badge(status: str) -> str:
    icon, color = STATUS_STYLE.get(status, ("•", "#6b7280"))
    return f"<span style='color:{color};font-weight:600'>{icon} {status.upper()}</span>"


def money(amount, currency="USD") -> str:
    try:
        return f"{currency} {amount:,.2f}"
    except (TypeError, ValueError):
        return str(amount)


@st.cache_resource
def _db():
    return get_db()


def quick_seed() -> None:
    """One-click 'seed if empty' — a light seed straight from the UI."""
    db = _db()
    accts = build_accounts(30)
    db.accounts.insert_many(accts)
    db.payment_instruments.insert_many(build_instruments(accts))
    db.merchants.insert_many(build_merchants())
    for _ in range(120):
        generate_event(db)
    take_snapshot(db)


# ── Sidebar: connection, seeding, simulator controls ───────────────────────

def render_sidebar() -> dict:
    st.sidebar.markdown("## 💳 Northstar Payments")
    st.sidebar.caption("Multi-region authorization control center")

    try:
        db = _db()
        db.command("ping")
        cs = supports_change_streams()
        st.sidebar.success(f"Atlas connected · `{db_name()}`")
        st.sidebar.caption(
            ("🔄 Change streams available — live feed uses rerun-safe polling."
             if cs else "🔁 Polling mode (standalone server — no change streams).")
        )
    except Exception as e:
        st.sidebar.error(f"Not connected: {e}")
        st.stop()

    if is_empty():
        st.sidebar.warning("No data yet. Seed to begin.")
        if st.sidebar.button("🌱 Seed demo data", use_container_width=True):
            with st.spinner("Seeding synthetic accounts and authorizations…"):
                quick_seed()
            st.rerun()
        st.stop()

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎛️ Simulator")
    mode = st.sidebar.radio("Traffic mode", ["Off", "Normal", "Burst"],
                            horizontal=True,
                            help="Normal ≈ steady flow · Burst ≈ high volume")
    impair = st.sidebar.selectbox(
        "Region impairment", ["None"] + REGIONS,
        help="Impaired region reroutes its traffic to a partner region.")
    if st.sidebar.button("⚡ Generate one batch now", use_container_width=True):
        _step_simulator("Burst" if mode == "Off" else mode,
                        None if impair == "None" else impair)
        st.toast("Generated a batch of authorizations")

    st.sidebar.markdown("---")
    auto = st.sidebar.checkbox("Auto-refresh", value=(mode != "Off"))
    interval = st.sidebar.slider("Refresh seconds", 1, 10, 2)
    st.sidebar.markdown("---")
    page = st.sidebar.radio("View", ["📊 Dashboard", "🔎 Transaction Explorer",
                                     "🏦 Accounts", "🧬 Payment Types & Schema"])
    return {"mode": mode, "impair": None if impair == "None" else impair,
            "auto": auto, "interval": interval, "page": page}


def _step_simulator(mode: str, impair) -> None:
    """Write a batch of events to Atlas for the current tick."""
    if mode == "Off":
        return
    db = _db()
    from lib.atlas_client import batch_size
    count = batch_size() * (5 if mode == "Burst" else 1)
    for _ in range(count):
        generate_event(db, impaired_region=impair)


# ── Page: Dashboard ────────────────────────────────────────────────────────

def render_dashboard() -> None:
    db = _db()
    st.markdown("## 📊 Live Authorization Dashboard")
    m = queries.dashboard_metrics(db, window_minutes=10)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Approval rate", f"{m['approval_rate']:.1f}%")
    c2.metric("Transactions / min", f"{m['tpm']:.1f}")
    c3.metric("Avg auth latency", f"{m['avg_latency_ms']:.0f} ms")
    c4.metric("Pending holds", m["pending"])
    c5.metric("Rerouted (failover)", m["rerouted"])

    if m["rerouted"]:
        st.warning(f"⚠️ {m['rerouted']} authorizations were rerouted in the last "
                   "10 min — a region is being impaired. Open the Metrics page in "
                   "Atlas to correlate with cluster activity.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Live feed")
        feed = queries.recent_feed(db, limit=25)
        for d in feed:
            with st.container(border=True):
                top = st.columns([3, 2, 2, 2])
                top[0].markdown(f"**{d.get('merchant_name', '?')}**  \n"
                                f"<span style='color:#6b7280'>{PAYMENT_LABELS.get(d['payment_type'], d['payment_type'])}</span>",
                                unsafe_allow_html=True)
                top[1].markdown(money(d["amount"], d.get("currency", "USD")))
                top[2].markdown(status_badge(d["auth_status"]), unsafe_allow_html=True)
                route = d.get("routing_region") or d.get("region")
                label = f"🌐 {d.get('region')}"
                if d.get("failover_reason"):
                    label += f" → {route}"
                top[3].markdown(f"<span style='color:#6b7280'>{label}</span>",
                                unsafe_allow_html=True)
                if d.get("risk_flags"):
                    st.caption("🚩 " + "  ".join(d["risk_flags"]))
    with right:
        st.markdown("#### Regional volume")
        rb = queries.regional_breakdown(db, window_minutes=10)
        if rb:
            df = pd.DataFrame(rb).set_index("region")
            st.bar_chart(df["volume"], height=200)
            st.dataframe(df[["approval_rate", "avg_latency_ms"]],
                         use_container_width=True)

        st.markdown("#### 🚩 Risk flags (last 60 min)")
        rf = queries.risk_flag_counts(db, window_minutes=60)
        if rf:
            st.dataframe(pd.DataFrame(rf).set_index("flag"),
                         use_container_width=True)
        else:
            st.caption("No risk flags raised recently.")


# ── Page: Transaction Explorer ─────────────────────────────────────────────

def render_explorer() -> None:
    db = _db()
    st.markdown("## 🔎 Transaction Explorer")
    f1, f2, f3, f4, f5 = st.columns(5)
    merchant = f1.text_input("Merchant contains")
    region = f2.selectbox("Region", [""] + REGIONS)
    status = f3.selectbox("Status", ["", "approved", "declined", "pending"])
    ptype = f4.selectbox("Payment type", [""] + list(PAYMENT_LABELS.keys()))
    token = f5.text_input("Card token contains")

    rows = queries.search_transactions(
        db, merchant=merchant, region=region, status=status,
        payment_type=ptype, token=token, limit=200)
    st.caption(f"{len(rows)} matching authorizations")

    if rows:
        table = [{
            "when": r["decided_at"].strftime("%H:%M:%S"),
            "merchant": r.get("merchant_name"),
            "type": r["payment_type"],
            "amount": r["amount"],
            "currency": r.get("currency"),
            "status": r["auth_status"],
            "region": r.get("region"),
            "request_id": r["request_id"],
        } for r in rows]
        st.dataframe(pd.DataFrame(table), use_container_width=True, height=320)

        ids = [r["request_id"] for r in rows]
        chosen = st.selectbox("Inspect a transaction", ids)
        if chosen:
            _render_transaction_detail(chosen)


def _render_transaction_detail(request_id: str) -> None:
    detail = queries.transaction_detail(_db(), request_id)
    decision, request = detail["decision"], detail["request"]
    if not decision:
        st.info("Transaction not found.")
        return
    st.markdown("### Transaction detail")
    a, b = st.columns(2)
    with a:
        st.markdown(status_badge(decision["auth_status"]), unsafe_allow_html=True)
        st.write(f"**Merchant:** {decision.get('merchant_name')} "
                 f"({decision.get('merchant_category')})")
        st.write(f"**Amount:** {money(decision['amount'], decision.get('currency'))}")
        st.write(f"**Card token:** `{decision.get('instrument_token')}`")
        st.write(f"**Masked card:** {decision.get('masked_number')}")
        st.write(f"**Region:** {decision.get('region')} → "
                 f"{decision.get('routing_region')}")
        if decision.get("failover_reason"):
            st.warning(f"Failover: {decision['failover_reason']}")
        if decision.get("decline_reason"):
            st.error(f"Decline reason: {decision['decline_reason']}")
        if decision.get("risk_flags"):
            st.write("**Risk flags:** " + ", ".join(decision["risk_flags"]))
    with b:
        st.markdown("**Raw request payload (varies by payment type)**")
        st.json(request.get("payload", {}) if request else {})
        st.markdown("**Ledger events**")
        st.json([{k: v for k, v in e.items() if k != "_id"}
                 for e in detail["ledger"]])


# ── Page: Accounts ─────────────────────────────────────────────────────────

def render_accounts() -> None:
    db = _db()
    st.markdown("## 🏦 Account & Balance View")
    accts = queries.list_accounts(db)
    labels = {f"{a['account_id']} — {a['holder_name']} ({a['region']})":
              a["account_id"] for a in accts}
    if not labels:
        st.info("No accounts. Seed data first.")
        return
    chosen = st.selectbox("Select an account", list(labels.keys()))
    ov = queries.account_overview(db, labels[chosen])
    acct = ov["account"]
    if not acct:
        return

    c1, c2, c3, c4 = st.columns(4)
    cur = acct.get("currency", "USD")
    c1.metric("Available balance", money(acct.get("available_balance"), cur))
    c2.metric("Pending holds", money(acct.get("hold_amount"), cur))
    c3.metric("Credit limit", money(acct.get("credit_limit"), cur))
    c4.metric("Tier", acct.get("tier", "-").title())

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### Recent authorizations")
        for d in ov["recent_auths"]:
            st.markdown(
                f"- {d['decided_at'].strftime('%H:%M:%S')} · "
                f"{money(d['amount'], d.get('currency'))} · "
                f"{d.get('merchant_name')} · "
                f"{status_badge(d['auth_status'])}", unsafe_allow_html=True)
    with right:
        st.markdown("#### Recent settlements")
        for e in ov["settlements"]:
            st.markdown(f"- {e['created_at'].strftime('%H:%M:%S')} · "
                        f"{money(e['amount'], e.get('currency'))}")
        st.markdown("#### Active holds")
        if ov["holds"]:
            for e in ov["holds"]:
                st.markdown(f"- {e['created_at'].strftime('%H:%M:%S')} · "
                            f"{money(e['amount'], e.get('currency'))}")
        else:
            st.caption("No holds on this account.")


# ── Page: Payment Types & Schema ───────────────────────────────────────────

def render_schema() -> None:
    db = _db()
    st.markdown("## 🧬 Payment Types & the Flexible Document Model")
    st.markdown(
        "Every authorization lands in one logical workflow, yet each payment "
        "event carries a **different payload shape** — with no schema migration "
        "and no nullable-column sprawl. Atlas stores them side by side.")

    mix = queries.payment_type_mix(db, window_minutes=120)
    if mix:
        cols = st.columns(len(mix))
        for col, row in zip(cols, mix):
            col.metric(PAYMENT_LABELS.get(row["payment_type"], row["payment_type"]),
                       row["count"])

    st.markdown("#### One workflow, three payloads")
    for ptype, label in PAYMENT_LABELS.items():
        sample = db.auth_requests.find_one({"payment_type": ptype})
        with st.expander(label, expanded=(ptype == "installment")):
            if sample:
                st.json(sample.get("payload", {}))
            else:
                st.caption("No sample yet — generate more traffic.")
    st.info("Adding a brand-new payment type is an application change, not a "
            "database migration — the same collection absorbs the new shape.")


# ── Main router ────────────────────────────────────────────────────────────

def main() -> None:
    cfg = render_sidebar()
    # Each rerun writes one tick of traffic when the simulator is active.
    if cfg["mode"] != "Off":
        _step_simulator(cfg["mode"], cfg["impair"])

    page = cfg["page"]
    if page.startswith("📊"):
        render_dashboard()
    elif page.startswith("🔎"):
        render_explorer()
    elif page.startswith("🏦"):
        render_accounts()
    else:
        render_schema()

    st.markdown("---")
    st.caption("Illustrative demo — MongoDB Atlas is the system of record. "
               "Not a performance benchmark or compliance certification harness.")

    if cfg["auto"]:
        time.sleep(cfg["interval"])
        st.rerun()


main()
