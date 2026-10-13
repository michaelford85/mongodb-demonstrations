"""Voyage AI embedding evaluation — a guided GUI.

Configure -> Run -> Results. Opening this page never calls an embedding API or
touches Atlas: a live run only starts after an explicit button press, and the
default mode is an offline dry run on synthetic data.
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from lib.config import (SUPPORTED_DATASETS, ConfigError, EvalError, RunParams, load_settings, redacted,
                        status_rows, validate_live)
from lib.pipeline import run_evaluation

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(page_title="Embedding Evaluation", page_icon="📐", layout="wide")

METRIC_HELP = {
    "NDCG@k": "Rewards putting relevant documents near the top; uses graded relevance when available. 1.0 is a perfect ordering.",
    "Recall@k": "Share of all relevant documents that appear in the top k.",
    "Precision@k": "Share of the top k that are relevant (divides by k even if fewer were returned).",
    "MRR": "Average of 1 / (rank of the first relevant result) — how quickly the first good hit appears.",
    "MAP": "Mean average precision: rewards ranking all relevant documents high, not just the first.",
}
MODE_DRY = "Dry run — synthetic data, no network, no cost"
MODE_LIVE = "Live — real embedding calls and writes to Atlas"
LABELS = {"voyage": "Voyage AI", "competitor": "Competitor"}


def load_config():
    try:
        return load_settings(), None
    except ConfigError as exc:
        return None, str(exc)


settings, config_error = load_config()

st.title("📐 Embedding retrieval evaluation")
st.caption("Compare Voyage AI with one other embedding model on the same public benchmark, "
           "using Atlas Vector Search. Metrics measure retrieval quality only — not answer quality.")

if config_error:
    st.error(f"Configuration problem: {config_error}")
    st.stop()

tab_config, tab_run, tab_results = st.tabs(["1 · Configuration", "2 · Run", "3 · Results"])

# ───────────────────────── 1. Configuration ─────────────────────────
with tab_config:
    st.subheader("Check your setup")
    st.write("Values are read from your local `.env` file (see `.env.example`). "
             "Secret values are never displayed — only whether they are set.")
    st.dataframe(pd.DataFrame(status_rows(settings)), hide_index=True, width="stretch")
    problems = validate_live(settings)
    if problems:
        st.warning("Live runs are disabled until these are fixed:\n\n" + "\n".join(f"- {p}" for p in problems))
        st.info("You can still try the **dry run** in step 2 to see the whole workflow with synthetic data.")
    else:
        st.success("Configuration looks complete for a live run.")

    with st.expander("What Atlas needs (index and cluster setup)"):
        st.markdown(
            """
- An Atlas cluster that supports **Vector Search** (M0 works, but allows only **3** search indexes in total —
  this demo creates **2 per run configuration**; use `scripts/cleanup.py` between configurations).
- A database user with `readWrite` on the demo database, and your IP on the Atlas **access list**.
- Indexes are created **for you** when you start a live run. Each model gets its own collection and its own index,
  so vectors from different models are never mixed. The dimension is read from a real embedding, not assumed:
            """
        )
        st.code(json.dumps({"fields": [{"type": "vector", "path": "embedding",
                                        "numDimensions": "<detected from the model>",
                                        "similarity": "cosine"}]}, indent=2), language="json")
        st.markdown("Index builds usually take under a minute; the run waits until each index is queryable.")

    with st.expander("Run configuration (secrets removed)"):
        st.json(redacted(settings, settings.defaults))

# ───────────────────────── 2. Run ─────────────────────────
with tab_run:
    st.subheader("Choose what to evaluate")
    d = settings.defaults
    mode = st.radio("Mode", [MODE_DRY, MODE_LIVE], index=0,
                    help="The dry run uses fake embeddings on a tiny made-up corpus so you can see the workflow.")
    live = mode == MODE_LIVE
    c1, c2 = st.columns(2)
    with c1:
        dataset = st.selectbox("Benchmark dataset", SUPPORTED_DATASETS,
                               index=SUPPORTED_DATASETS.index(d.dataset) if d.dataset in SUPPORTED_DATASETS else 0,
                               disabled=not live, help="Public BEIR datasets, downloaded on first live run.")
        num_queries = st.slider("Number of queries", 5, 300, min(max(d.num_queries, 5), 300), disabled=not live)
    with c2:
        max_docs = st.slider("Corpus size (documents)", 100, 5000, min(max(d.max_docs, 100), 5000), step=100,
                             disabled=not live,
                             help="All relevant documents for the sampled queries are always included.")
        seed = st.number_input("Random seed", value=d.seed, step=1, disabled=not live)
    k_options = [1, 3, 5, 10, 20]
    ks = st.multiselect("Cutoffs (k)", k_options, default=[k for k in d.k_values if k in k_options] or [5, 10],
                        help="Retrieval depth is the largest k. Every model is scored at the same cutoffs.")

    params = RunParams(dataset=dataset, num_queries=int(num_queries), max_docs=int(max_docs),
                       seed=int(seed), k_values=tuple(sorted(ks)))
    st.markdown(f"**Models:** Voyage AI `{settings.voyage.model}` vs. "
                f"{settings.competitor.provider} `{settings.competitor.model or '(not set)'}` "
                "— change these in `.env`.")
    if live:
        st.markdown(f"This will embed about **{params.max_docs + params.num_queries} texts per model** "
                    "(documents + queries), then create 2 collections and 2 vector indexes in Atlas. "
                    "Embedding calls may incur charges with each provider.")
        confirmed = st.checkbox("I understand this calls paid APIs and writes to my Atlas cluster.")
    else:
        confirmed = True

    param_problems = params.validate()
    for p in param_problems:
        st.error(p)
    blocked = bool(param_problems) or (live and (bool(problems) or not confirmed))
    if live and problems:
        st.caption("Live run disabled — see the Configuration tab.")

    b1, b2 = st.columns(2)
    run_clicked = b1.button("▶ Run evaluation", type="primary", disabled=blocked)
    last = st.session_state.get("last_run")
    rerun_clicked = b2.button("↻ Rerun with the same settings", disabled=blocked or last is None,
                              help="Repeats the previous run's settings exactly.")

    if run_clicked or rerun_clicked:
        run_params, run_live = (params, live) if run_clicked else (last["params"], last["live"])
        st.session_state["last_run"] = {"params": run_params, "live": run_live}
        bar = st.progress(0.0, text="Starting…")
        try:
            result = run_evaluation(settings, run_params, mock=not run_live,
                                    progress=lambda frac, msg: bar.progress(min(max(frac, 0.0), 1.0), text=msg))
            st.session_state["result"] = result
            st.session_state.pop("error", None)
            st.session_state["notice"] = "Run completed. Open the **3 · Results** tab."
        except EvalError as exc:
            st.session_state["error"] = str(exc)
            st.session_state.pop("notice", None)
        except Exception as exc:  # unexpected: show the type only, never a raw message that could echo a URI
            st.session_state["error"] = f"Unexpected error ({type(exc).__name__}). Check your settings and try again."
            st.session_state.pop("notice", None)
        st.rerun()  # refresh so the rerun button reflects the run just stored
    if st.session_state.get("notice"):
        st.success(st.session_state["notice"])
    if st.session_state.get("error"):
        st.error(st.session_state["error"])

# ───────────────────────── 3. Results ─────────────────────────
with tab_results:
    result = st.session_state.get("result")
    if not result:
        st.info("No results yet. Run an evaluation in step 2 (the dry run needs no setup).")
    else:
        ds, ks_run, depth = result["dataset"], result["ks"], result["depth"]
        if result["mock"]:
            st.warning("**Dry run** — synthetic data and fake embeddings. These numbers are not real model quality.")
        m = result["models"]
        cols = st.columns(4)
        cols[0].metric("Status", result["status"].capitalize())
        cols[1].metric("Dataset", ds["name"])
        cols[2].metric("Queries / documents", f"{ds['queries']} / {ds['documents']}")
        cols[3].metric("Cutoffs (k)", ", ".join(map(str, ks_run)))
        st.caption(f"Voyage AI: `{m['voyage']['model']}` ({m['voyage']['dimensions']} dims) · "
                   f"Competitor: `{m['competitor']['provider']}:{m['competitor']['model']}` "
                   f"({m['competitor']['dimensions']} dims) · {result['elapsed_seconds']} s")

        # Comparison table: text markers so the leader never depends on colour.
        rows, chart_rows = [], []
        for metric in m["voyage"]["aggregate"]:
            v, c = m["voyage"]["aggregate"][metric], m["competitor"]["aggregate"][metric]
            lead = "Voyage AI ▲" if v - c > 1e-9 else "Competitor ▲" if c - v > 1e-9 else "tie ="
            rows.append({"Metric": metric, "Voyage AI": round(v, 4), "Competitor": round(c, 4),
                         "Difference (Voyage − Competitor)": round(v - c, 4), "Higher": lead})
            for role in ("voyage", "competitor"):
                chart_rows.append({"Metric": metric, "Model": LABELS[role],
                                   "Score": m[role]["aggregate"][metric]})
        st.subheader("Metrics")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        chart = alt.Chart(pd.DataFrame(chart_rows)).mark_bar().encode(
            x=alt.X("Metric:N", sort=None, title=None, axis=alt.Axis(labelAngle=-30)),
            xOffset="Model:N",
            y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 1]), title="Score (higher is better)"),
            color=alt.Color("Model:N", legend=alt.Legend(title="Model")),
            tooltip=["Metric", "Model", alt.Tooltip("Score:Q", format=".3f")],
        )
        labels = alt.Chart(pd.DataFrame(chart_rows)).mark_text(dy=-6, fontSize=11, color="#888888").encode(
            x=alt.X("Metric:N", sort=None), xOffset="Model:N", y="Score:Q", text=alt.Text("Score:Q", format=".2f"))
        st.altair_chart(chart + labels, width="stretch")

        st.subheader("How consistent is the difference?")
        metric_names = list(m["voyage"]["aggregate"])
        default = result["primary_metric"] if result["primary_metric"] in metric_names else metric_names[0]
        pick = st.selectbox("Metric", metric_names, index=metric_names.index(default))
        cmp_ = result["comparisons"][pick]
        if cmp_["n"]:
            a, b, c3 = st.columns(3)
            a.metric("Queries where Voyage AI scored higher", cmp_["wins_a"])
            b.metric("Queries where Competitor scored higher", cmp_["wins_b"])
            c3.metric("Ties", cmp_["ties"])
            st.write(f"Mean difference (Voyage − Competitor) on **{pick}**: **{cmp_['mean_diff']:+.4f}**, "
                     f"bootstrap 95% interval [{cmp_['ci_low']:+.4f}, {cmp_['ci_high']:+.4f}] over {cmp_['n']} queries. "
                     "If the interval includes 0, this sample does not separate the models.")

        st.subheader("Per-query results")
        only_diff = st.checkbox("Show only queries where the models differ")
        pq_rows = []
        for row in result["per_query"]:
            vm, cm = row["voyage"]["metrics"][pick], row["competitor"]["metrics"][pick]
            if only_diff and abs(vm - cm) <= 1e-9:
                continue
            pq_rows.append({"Query": row["query"], "Relevant docs": row["n_relevant"],
                            f"Voyage {pick}": round(vm, 3), f"Competitor {pick}": round(cm, 3),
                            "Voyage first-hit rank": row["voyage"]["first_relevant_rank"],
                            "Competitor first-hit rank": row["competitor"]["first_relevant_rank"]})
        st.dataframe(pd.DataFrame(pq_rows), hide_index=True, width="stretch")

        with st.expander("What do these metrics mean?"):
            for name, text in METRIC_HELP.items():
                st.markdown(f"**{name}** — {text}")
            st.markdown(f"MRR and MAP use the top {depth} results.")

        with st.expander("Atlas query and index used (per model)"):
            for role in ("voyage", "competitor"):
                st.markdown(f"**{LABELS[role]}** — collection `{m[role]['collection']}`, "
                            f"index `{m[role]['index_name']}`")
                st.code(json.dumps(m[role]["index_definition"], indent=2), language="json")
                st.code(json.dumps(m[role]["pipeline_template"], indent=2), language="json")
            st.caption("Same pipeline, limit and numCandidates for both models; only the vectors differ.")

        with st.expander("Run configuration (secrets removed)"):
            st.json(result["config"])

        st.subheader("Caveats")
        for caveat in result["caveats"]:
            st.markdown(f"- {caveat}")

        st.download_button("Download results (JSON, no secrets)", json.dumps(result, indent=2),
                           file_name="embedding_eval_results.json", mime="application/json")
