"""The agent loop: plan, act, observe, answer.

One operator turn drives up to MAX_STEPS iterations of:

  plan     ask the model which tool to call, given the catalogue, the recent
           transcript, the ticket ids currently in context, and anything
           already observed this turn.
  act      validate the arguments against the tool schema and run it. A bad
           tool name or a bad argument becomes an observation, not a crash —
           that is what lets the model correct itself on the next step.
  observe  append the result to this turn's observations.

Then a second, separate call composes the answer from the observations only.
Splitting planning from answering keeps each prompt small and makes the
demonstration legible: you can see exactly what the model decided, and
separately what it said about the results.

Both prompts carry machine-readable markers (MODE, OPERATOR, OBSERVATIONS,
CONTEXT_TICKET_IDS) so the offline planner can read the same prompt the real
model gets.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import tools  # noqa: E402

PLAN_SYSTEM = """You are a support-operations agent working over a MongoDB \
collection of support tickets. MODE: plan

You cannot see the tickets. The only way to learn anything is to call one of \
these tools:

{catalogue}

Choose the single most useful next tool call. Reply with JSON only:

  {{"thought": "one sentence on why", "tool": "<name>", "arguments": {{...}}}}

If the OBSERVATIONS already answer the operator, or no tool applies, reply:

  {{"thought": "one sentence on why", "done": true}}

Rules:
- Use only the tools and parameter names listed above.
- Never invent ticket ids. If the operator says "that one" or "the second one",
  resolve it against CONTEXT_TICKET_IDS, in order.
- One tool per reply. Do not repeat a call already in OBSERVATIONS."""

ANSWER_SYSTEM = """You are a support-operations agent. MODE: answer

Answer the operator using only the OBSERVATIONS below. They are the output of \
tools you just ran against a MongoDB ticket collection.

Reply with JSON only:

  {"answer": "your reply to the operator"}

Rules:
- Cite ticket ids when you mention a ticket.
- State counts exactly as observed; never estimate.
- If the observations are empty or errored, say so plainly and suggest what to
  ask instead. Do not guess."""


def _prompt(operator: str, observations: list, context_ids: list) -> str:
    parts = [f"OPERATOR: {operator}"]
    if context_ids:
        parts.append("CONTEXT_TICKET_IDS: " + ", ".join(context_ids))
    parts.append("OBSERVATIONS: " + json.dumps(observations, default=str))
    return "\n".join(parts)


class Agent:
    def __init__(self, session: memory.Session = None, trace=None):
        self.session = session or memory.Session()
        self.trace = trace if trace is not None else _print_trace

    def _emit(self, kind: str, payload) -> None:
        if self.trace and config.SHOW_TRACE:
            self.trace(kind, payload)

    def ask(self, operator: str) -> str:
        """Run one operator turn to completion and return the agent's answer."""
        turn = self.session.begin_turn(operator)
        context_ids = self.session.context_ticket_ids()
        history = self.session.history(exclude=turn)

        for step_no in range(1, config.MAX_STEPS + 1):
            observations = turn.observations()
            messages = history + [{
                "role": "user",
                "content": _prompt(operator, observations, context_ids),
            }]
            try:
                decision = llm.complete_json(
                    PLAN_SYSTEM.format(catalogue=tools.catalogue()), messages)
            except ValueError as exc:
                self._emit("error", str(exc))
                break

            thought = decision.get("thought", "")
            name = decision.get("tool")
            if thought:
                self._emit("thought", f"[step {step_no}] {thought}")

            if decision.get("done") or not name:
                break

            arguments = decision.get("arguments") or {}
            self._emit("tool", f"{name}({json.dumps(arguments)})")

            step = {"thought": thought, "tool": name, "arguments": arguments}
            try:
                step["result"] = tools.get(name).call(arguments)
                self._emit("observation", step["result"].get("summary", ""))
            except (KeyError, ValueError) as exc:
                step["error"] = str(exc).strip("'")
                self._emit("error", step["error"])
            self.session.record_step(turn, step)

        answer = self._compose(operator, turn)
        self.session.record_answer(turn, answer)
        return answer

    def _compose(self, operator: str, turn: memory.Turn) -> str:
        observations = turn.observations()
        messages = [{"role": "user",
                     "content": _prompt(operator, observations, [])}]
        try:
            reply = llm.complete_json(ANSWER_SYSTEM, messages)
        except ValueError as exc:
            self._emit("error", str(exc))
            return "I could not put an answer together for that."
        return (reply.get("answer") or "").strip() or \
            "I found nothing to report for that."


_TRACE_PREFIX = {"thought": "  ~", "tool": "  >", "observation": "  =",
                 "error": "  !"}


def _print_trace(kind: str, payload) -> None:
    print(f"{_TRACE_PREFIX.get(kind, '  .')} {payload}")
