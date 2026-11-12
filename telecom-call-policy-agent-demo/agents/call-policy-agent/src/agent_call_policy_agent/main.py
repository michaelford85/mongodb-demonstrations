"""
Call Policy Agent - Atlas Agent Engine demo for a fictional Intelligent Call
Control (call-control) policy lifecycle.

ALL DATA AND RULES IN THIS DEMO ARE FICTIONAL, created for a technical
discussion. This demo does not represent any organization.s actual policies, data
model, architecture, or security controls.

The agent helps an operator author and manage call-control policy changes:

  operator request -> retrieve synthetic context via explicit tools
    -> draft a structured policy change (constrained demo DSL)
    -> validate schema and permitted transitions
    -> dry-run old vs. proposed policy over sample calls
    -> request human approval (native Agent Engine suspend/resume)
    -> publish a versioned policy record + audit trail (only after approval)

Call evaluation is deterministic and lives in evaluator.py; it never calls
an LLM. The agent is for authoring/governance, not the live call path.

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

from agent_call_policy_agent.dsl import validate_policy
from agent_call_policy_agent.evaluator import compare_policies, evaluate_call
from agent_call_policy_agent.llm import build_llm
from agent_call_policy_agent.store import DEMO_DATABASE_DEFAULT, create_store

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

APP_NAME = "Call Policy Agent (Fictional Demo)"

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
def get_enterprise_profile(enterprise_id: str) -> str:
    """Retrieve the (fictional) enterprise profile used by the demo call-control rules."""
    record = store.get_enterprise(enterprise_id)
    if not record:
        return json.dumps({"error": f"No enterprise {enterprise_id} in demo data"})
    return json.dumps(record, indent=2)


@app.tool()
def list_carrier_relationships(enterprise_id: str) -> str:
    """List the (fictional) carrier relationships for an enterprise."""
    return json.dumps(store.list_carrier_relationships(enterprise_id), indent=2)


@app.tool()
def get_brand_metadata(enterprise_id: str) -> str:
    """List the (fictional) approved brand metadata for an enterprise."""
    return json.dumps(store.list_brand_metadata(enterprise_id), indent=2)


@app.tool()
def get_active_policy() -> str:
    """Return the currently active (fictional) call-control policy snapshot."""
    policy = store.get_active_policy()
    if not policy:
        return json.dumps({"error": "No active policy published yet"})
    return json.dumps(policy, indent=2)


@app.tool()
def list_sample_calls() -> str:
    """List the synthetic sample call requests used for dry runs."""
    return json.dumps(store.list_sample_calls(), indent=2)


# =============================================================================
# Drafting, validation, simulation
# =============================================================================


@app.tool()
def submit_policy_draft(
    policy_id: str,
    label: str,
    rules: str,
    default_action: str,
    rationale: str,
    source_notes: str,
) -> str:
    """Submit a proposed call-control policy draft for validation.

    Args:
        policy_id: Policy identifier, e.g. 'demo-call-policy'.
        label: Short human-readable label for the change.
        rules: JSON array of rules. Each rule: {"rule_id", "priority" (int),
            "match" (object; optional keys: enterprise_id, carrier_id, trunk_id,
            origin_countries (2-letter ISO list), number_prefix ("+1..." prefix)),
            "action" ("deliver" | "deliver_with_brand" | "block"),
            optional "brand_id" (required for deliver_with_brand), "rationale"}.
        default_action: "deliver" | "deliver_with_brand" | "block" (no rule matched).
        rationale: Why this change is being proposed.
        source_notes: Which demo context records support the change.
    """
    try:
        parsed_rules = json.loads(rules)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"rules is not valid JSON: {exc}"})

    enterprise_ids = {d["enterprise_id"] for d in store.list_catalog("enterprises")}
    brand_ids = {d["brand_id"] for d in store.list_catalog("brand_metadata")}
    draft = {
        "draft_id": _next_draft_id(),
        "policy_id": policy_id,
        "label": label,
        "status": "draft",
        "rules": parsed_rules,
        "default_action": default_action,
        "rationale": rationale,
        "source_notes": source_notes,
        "note": "Fictional demo policy - synthetic data only",
    }
    errors = validate_policy(draft, brand_ids=brand_ids, enterprise_ids=enterprise_ids)
    if errors:
        store.audit("validation_failed", {"policy_id": policy_id, "errors": errors})
        return json.dumps({"validation": "failed", "errors": errors}, indent=2)

    saved = store.save_draft(draft)
    store.audit("validation_passed", {"draft_id": saved["draft_id"]})
    return json.dumps(
        {"validation": "passed", "draft_id": saved["draft_id"], "status": saved["status"]},
        indent=2,
    )


@app.tool()
def simulate_policy(draft_id: str) -> str:
    """Dry-run the proposed draft against the active policy over sample calls."""
    draft = store.get_draft(draft_id)
    if not draft:
        return json.dumps({"error": f"Unknown draft: {draft_id}"})
    active = store.get_active_policy()
    proposed = {
        "policy_version": "proposed",
        "rules": draft["rules"],
        "default_action": draft.get("default_action", "block"),
    }
    result = compare_policies(active or {"policy_version": 0, "rules": []}, proposed, store.list_sample_calls())
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
            "description": "Approve or deny activation of the proposed call-control policy.",
            "enum": ["approved", "denied"],
        },
        "approver": {"type": "string", "title": "Approver name"},
        "notes": {"type": "string", "title": "Reviewer notes"},
    },
    "additionalProperties": False,
}


@app.tool()
def request_policy_approval(draft_id: str, summary: str) -> str:
    """SUSPEND execution and request human approval to activate a policy draft.

    Use this ONLY after the draft passed validation and the operator has seen
    the before/after dry run. Execution stops here until a human decides.
    """
    store.request_approval(draft_id, summary)
    answer = interrupt(
        {
            "action": "approve_policy_activation",
            "draft_id": draft_id,
            "summary": summary,
            "message": "Human approval required before the proposed call-control policy can be activated.",
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
            "message": "Approval recorded. Call publish_policy to activate the new version.",
        },
        indent=2,
    )


@app.tool()
def publish_policy(draft_id: str) -> str:
    """Publish an APPROVED draft as a new active policy version.

    Refuses to publish without a recorded human approval decision.
    """
    try:
        published = store.publish(draft_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, indent=2)
    return json.dumps(
        {
            "status": "published",
            "policy_id": published["policy_id"],
            "policy_version": published["policy_version"],
            "approved_by": published["approved_by"],
            "message": "New active policy version recorded. Call evaluate_call to test it.",
        },
        indent=2,
    )


# =============================================================================
# Deterministic call evaluation (no LLM on this path)
# =============================================================================


@app.tool()
def evaluate_call_tool(from_number: str, carrier_id: str, origin_country: str, trunk_id: str = "", enterprise_id: str = "") -> str:
    """Deterministically evaluate one call against the ACTIVE policy snapshot.

    This tool does NOT use any model: it reads the published policy and
    returns the decision, matched rule, and reason, mirroring the live
    call path.
    """
    active = store.get_active_policy()
    if not active:
        return json.dumps({"error": "No active policy published yet"})
    call = {
        "from_number": from_number,
        "carrier_id": carrier_id,
        "origin_country": origin_country,
        "trunk_id": trunk_id,
        "enterprise_id": enterprise_id or None,
    }
    return json.dumps(evaluate_call(active, call), indent=2)


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


SYSTEM_PROMPT = """You are the Call Policy Agent, an internal assistant for a
FICTIONAL Intelligent Call Control (call-control) policy lifecycle used in a technical
discussion. All data you can see is synthetic demo data.

## Your role
Help an operator author, validate, simulate, and (after explicit human
approval) activate call-control policy changes. You never make live call decisions
yourself; the live path uses a deterministic evaluator over the published
policy snapshot.

## Working rules
1. Start every request by retrieving context with the explicit tools:
   get_enterprise_profile, list_carrier_relationships, get_brand_metadata,
   get_active_policy, list_sample_calls. Cite the records you used.
2. Express proposals as the constrained demo DSL via submit_policy_draft.
   Never invent rule fields beyond the documented ones.
3. After a draft passes validation, run simulate_policy and show the
   before/after table to the operator.
4. Only after the operator confirms, call request_policy_approval. Execution
   will suspend until a human decides. NEVER publish without approval.
5. After approval, call publish_policy, then verify with evaluate_call_tool
   and show_audit_trail.
6. Always remind the user that all data and rules are fictional demo data.
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
