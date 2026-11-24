"""
Operational Change Assistant - Atlas Agent Engine demo (domain-neutral).

ALL DATA AND DIRECTIVES IN THIS DEMO ARE FICTIONAL, created for a technical
discussion. This demo does not represent any organization's actual
configuration, policies, data model, architecture, or security controls.

The agent helps an operator author and manage changes to a fictional operating
configuration:

  operator request -> retrieve synthetic context via explicit tools
    -> draft a structured configuration change (constrained demo DSL)
    -> validate schema and permitted transitions
    -> dry-run active vs. proposed configuration over sample cases
    -> request human approval (native Agent Engine suspend/resume)
    -> publish a versioned configuration record + audit trail (only after approval)

Request evaluation is deterministic and lives in evaluator.py; it never calls
an LLM. The agent is for authoring/governance, not the live request path.

RUNNER_MODE=aer            -> Full LangGraph execution
RUNNER_MODE=tool           -> Tool function execution
"""

import json
import logging
import os
import sys
from typing import Annotated, Any, Literal, Optional, TypedDict

from dotenv import load_dotenv

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from agent_engine_sdk_langgraph import App

from agent_change_ops_agent.dsl import validate_config
from agent_change_ops_agent.evaluator import compare_configs, evaluate_case
from agent_change_ops_agent.llm import build_llm
from agent_change_ops_agent.store import DEMO_DATABASE_DEFAULT, create_store

# =============================================================================
# Logging / Configuration
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)
load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", DEMO_DATABASE_DEFAULT)

APP_NAME = "Operational Change Assistant (Fictional Demo)"

app = App(app_name=APP_NAME)
logger.info("App created")

store = create_store(MONGODB_URI, MONGODB_DATABASE)
if store.mode == "mock":
    logger.warning(
        "*** MOCK MODE: no MONGODB_URI configured. Demo data is in-memory only. ***"
    )
store.ensure_seeded()

DRAFT_SEQUENCE = {"n": 0}


def _next_draft_id() -> str:
    DRAFT_SEQUENCE["n"] += 1
    return f"draft-{DRAFT_SEQUENCE['n']:03d}"


# =============================================================================
# Context retrieval tools (explicit, inspectable)
# =============================================================================


@app.tool()
def get_workspace_profile(workspace_id: str) -> str:
    """Retrieve the (fictional) workspace profile used by the demo configuration."""
    record = store.get_workspace(workspace_id)
    if not record:
        return json.dumps({"error": f"No workspace {workspace_id} in demo data"})
    return json.dumps(record, indent=2)


@app.tool()
def list_services(workspace_id: str) -> str:
    """List the (fictional) services registered to a workspace."""
    return json.dumps(store.list_services(workspace_id), indent=2)


@app.tool()
def get_active_config() -> str:
    """Return the currently active (fictional) operating configuration snapshot."""
    config = store.get_active_config()
    if not config:
        return json.dumps({"error": "No active configuration published yet"})
    return json.dumps(config, indent=2)


@app.tool()
def list_sample_cases() -> str:
    """List the synthetic sample cases used for dry runs."""
    return json.dumps(store.list_sample_cases(), indent=2)


@app.tool()
def search_change_notes(query: str) -> str:
    """Retrieve related synthetic change notes for a workspace, most relevant first.

    When the demo's Atlas Automated Embedding Vector Search index is available,
    this uses semantic retrieval ($vectorSearch with a text query; Atlas embeds
    the query automatically). Otherwise it falls back to deterministic keyword
    matching. Notes are context only: they never make or execute the decision.
    """
    results = store.vector_search_notes(query)
    retrieval = "vector (Atlas Automated Embedding)"
    if results is None:
        results = store.keyword_search_notes(query)
        retrieval = "keyword fallback (vector search unavailable)"
    return json.dumps(
        {"retrieval": retrieval, "count": len(results), "notes": results}, indent=2
    )


# =============================================================================
# Drafting, validation, simulation
# ==============================================================================


@app.tool()
def submit_change_draft(
    config_id: str,
    label: str,
    directives: str,
    default_action: str,
    rationale: str,
    source_notes: str,
) -> str:
    """Submit a proposed operating-configuration draft for validation.

    Args:
        config_id: Configuration identifier, e.g. 'demo-op-config'.
        label: Short human-readable label for the change.
        directives: JSON array of directives. Each directive:
            {"directive_id", "priority" (int), "match" (object; optional keys:
            service_id, request_type, region, environment),
            "action" ("allow" | "allow_with_tag" | "deny"),
            optional "tag_id" (required for allow_with_tag), "rationale"}.
        default_action: "allow" | "allow_with_tag" | "deny" (no directive matched).
        rationale: Why this change is being proposed.
        source_notes: Which demo context records support the change.
    """
    try:
        parsed_directives = json.loads(directives)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"directives is not valid JSON: {exc}"})

    service_ids = {d["service_id"] for d in store.list_catalog("services")}
    tag_ids = {d["tag_id"] for d in store.list_catalog("tag_metadata")}
    draft = {
        "draft_id": _next_draft_id(),
        "config_id": config_id,
        "label": label,
        "status": "draft",
        "directives": parsed_directives,
        "default_action": default_action,
        "rationale": rationale,
        "source_notes": source_notes,
        "note": "Fictional demo configuration - synthetic data only",
    }
    errors = validate_config(draft, tag_ids=tag_ids, service_ids=service_ids, require_version=False)
    if errors:
        store.audit("validation_failed", {"config_id": config_id, "errors": errors})
        return json.dumps({"validation": "failed", "errors": errors}, indent=2)

    saved = store.save_draft(draft)
    store.audit("validation_passed", {"draft_id": saved["draft_id"]})
    return json.dumps(
        {"validation": "passed", "draft_id": saved["draft_id"], "status": saved["status"]},
        indent=2,
    )


@app.tool()
def simulate_change(draft_id: str) -> str:
    """Dry-run the proposed draft against the active configuration over sample cases."""
    draft = store.get_draft(draft_id)
    if not draft:
        return json.dumps({"error": f"Unknown draft: {draft_id}"})
    active = store.get_active_config()
    proposed = {
        "config_version": "proposed",
        "directives": draft["directives"],
        "default_action": draft.get("default_action", "deny"),
    }
    result = compare_configs(active or {"config_version": 0, "directives": []}, proposed, store.list_sample_cases())
    store.audit("simulation_run", {"draft_id": draft_id, "changed": result["changed_count"]})
    return json.dumps({"draft_id": draft_id, **result}, indent=2)


# =============================================================================
# Human approval (native Agent Engine suspend/resume)
# =============================================================================

APPROVAL_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["decision"],
    "properties": {
        "decision": {
            "type": "string",
            "title": "Decision",
            "description": "Approve or deny activation of the proposed operating configuration.",
            "enum": ["approved", "denied"],
        },
        "approver": {"type": "string", "title": "Approver name"},
        "notes": {"type": "string", "title": "Reviewer notes"},
    },
    "additionalProperties": False,
}


@app.tool()
def request_change_approval(draft_id: str, summary: str) -> str:
    """SUSPEND execution and request human approval to activate a config draft.

    Use this ONLY after the draft passed validation and the operator has seen
    the before/after dry run. Execution stops here until a human decides.
    """
    store.request_approval(draft_id, summary)
    answer = interrupt(
        {
            "action": "approve_config_activation",
            "draft_id": draft_id,
            "summary": summary,
            "message": "Human approval required before the proposed operating configuration can be activated.",
            "response_schema": APPROVAL_RESPONSE_SCHEMA,
        }
    )
    if not isinstance(answer, dict):
        raise TypeError("approval resume value must be an object")
    decision = answer.get("decision")
    if decision not in ("approved", "denied"):
        raise ValueError("decision must be 'approved' or 'denied'")
    approver = str(answer.get("approver", "operator"))
    notes = str(answer.get("notes", ""))
    recorded = store.record_approval(draft_id, decision, approver, notes)

    if decision != "approved":
        return json.dumps(
            {
                "status": "denied",
                "draft_id": draft_id,
                "approval_id": recorded.get("approval_id"),
                "message": "The draft was NOT activated. Nothing was published.",
            },
            indent=2,
        )
    return json.dumps(
        {
            "status": "approved",
            "draft_id": draft_id,
            "approval_id": recorded.get("approval_id"),
            "message": "Approval recorded. Call publish_change to activate the new version.",
        },
        indent=2,
    )


@app.tool()
def publish_change(draft_id: str) -> str:
    """Publish an APPROVED draft as a new active configuration version.

    Refuses to publish without a recorded human approval decision.
    """
    try:
        published = store.publish(draft_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, indent=2)
    return json.dumps(
        {
            "status": "published",
            "config_id": published["config_id"],
            "config_version": published["config_version"],
            "approved_by": published["approved_by"],
            "message": "New active configuration version recorded. Call evaluate_case_tool to test it.",
        },
        indent=2,
    )


# =============================================================================
# Deterministic case evaluation (no LLM on this path)
# =============================================================================


@app.tool()
def evaluate_case_tool(
    service_id: str,
    request_type: str,
    region: str = "us-demo-1",
    environment: str = "prod",
    workspace_id: str = "demo_workspace_001",
) -> str:
    """Deterministically evaluate one sample request against the ACTIVE config snapshot.

    This tool does NOT use any model: it reads the published configuration and
    returns the outcome, matched directive, and reason, mirroring the live
    request path.
    """
    active = store.get_active_config()
    if not active:
        return json.dumps({"error": "No active configuration published yet"})
    case = {
        "service_id": service_id,
        "request_type": request_type,
        "region": region,
        "environment": environment,
        "workspace_id": workspace_id,
    }
    return json.dumps(evaluate_case(active, case), indent=2)


@app.tool()
def show_audit_trail() -> str:
    """Return the demo audit trail: drafts, validations, simulations, approvals, versions."""
    return json.dumps(store.audit_trail(), indent=2)


# =============================================================================
# Agent Definition (scaffold structure preserved)
# =============================================================================


class _AgentStateOptional(TypedDict, total=False):
    user_id: Optional[str]
    session_id: Optional[str]


class AgentState(_AgentStateOptional):
    messages: Annotated[list[BaseMessage], add_messages]


SYSTEM_PROMPT = """You are the Operational Change Assistant, an internal assistant for a
FICTIONAL operating-configuration change lifecycle used in a technical
discussion. All data you can see is synthetic demo data.

## Your role
Help an operator author, validate, simulate, and (after explicit human
approval) activate operating-configuration changes. You never make live
operational decisions yourself; the live path uses a deterministic evaluator
over the published configuration snapshot.

## Working rules
1. Start every request by retrieving context with the explicit tools:
   get_workspace_profile, list_services, get_active_config, list_sample_cases,
   and search_change_notes. Cite the records you used. If a tool returns an
   error or nothing useful, say so instead of guessing.
2. Express proposals as the constrained demo DSL via submit_change_draft.
   Never invent directive fields beyond the documented ones.
3. After a draft passes validation, run simulate_change and show the
   before/after table to the operator.
4. Only after the operator confirms, call request_change_approval. Execution
   will suspend until a human decides. NEVER publish without approval.
5. After approval, call publish_change, then verify with evaluate_case_tool
   and show_audit_trail.
6. Always remind the user that all data and directives are fictional demo data.
"""


@app.entrypoint
def build_agent(llm: Optional[BaseChatModel] = None) -> CompiledStateGraph:
    """Build the LangGraph agent."""
    logger.info("Building LangGraph agent...")
    if llm is None:
        llm = app.llm(build_llm())
    tools = app.get_tools()
    llm_with_tools = llm.bind_tools(app.get_tool_schemas())

    def agent_node(state: AgentState) -> AgentState:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> Literal["tools", "end"]:
        last = state["messages"][-1]
        return "tools" if hasattr(last, "tool_calls") and last.tool_calls else "end"  # type: ignore[union-attr]

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    builder.add_edge("tools", "agent")

    graph = builder.compile(checkpointer=app.checkpointer())
    logger.info("Agent graph compiled")
    return graph


def main():
    logger.info("=" * 60)
    logger.info(f"Starting {APP_NAME} (Runner SDK)")
    logger.info("=" * 60)
    app.run()


if __name__ == "__main__":
    main()
