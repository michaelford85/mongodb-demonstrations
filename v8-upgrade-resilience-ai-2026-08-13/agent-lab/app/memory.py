"""Short-term memory for one agent session.

Two things are remembered, and they are remembered for different reasons:

  transcript   the last MEMORY_TURNS operator/agent exchanges, replayed into
               the planning prompt so the model knows what was already asked.
  last_rows    the rows the most recent tool returned. This is what makes
               "tell me more about the second one" resolvable: the ticket ids
               are carried forward as CONTEXT_TICKET_IDS rather than the model
               being expected to remember them from prose.

Deliberately in-process and deliberately forgetful. Persisting memory to
MongoDB is the obvious next step and is called out in the README, but keeping
it in memory here makes the boundary between "the agent's state" and "the
database the agent queries" unambiguous during a demo.
"""
import config


class Turn:
    """One operator question and the agent's eventual answer."""

    def __init__(self, operator: str):
        self.operator = operator
        self.answer = ""
        self.steps = []  # [{"thought", "tool", "arguments", "result"|"error"}]

    def observations(self) -> list:
        """The tool results from this turn, in the shape the prompt expects."""
        return [
            {k: v for k, v in step.items() if k in
             ("tool", "arguments", "result", "error")}
            for step in self.steps if "tool" in step
        ]


class Session:
    def __init__(self, max_turns: int = None):
        self.max_turns = max_turns or config.MEMORY_TURNS
        self.turns = []
        self.last_rows = []

    # ── recording ────────────────────────────────────────────────────────────
    def begin_turn(self, operator: str) -> Turn:
        turn = Turn(operator)
        self.turns.append(turn)
        del self.turns[:-self.max_turns]
        return turn

    def record_step(self, turn: Turn, step: dict) -> None:
        turn.steps.append(step)
        rows = (step.get("result") or {}).get("rows")
        if rows:
            self.last_rows = rows

    def record_answer(self, turn: Turn, answer: str) -> None:
        turn.answer = answer

    def clear(self) -> None:
        self.turns.clear()
        self.last_rows = []

    # ── replay into the prompt ───────────────────────────────────────────────
    def context_ticket_ids(self) -> list:
        return [r["ticket_id"] for r in self.last_rows if r.get("ticket_id")]

    def history(self, exclude: Turn = None) -> list:
        """Prior exchanges as chat messages, oldest first."""
        messages = []
        for turn in self.turns:
            if turn is exclude:
                continue
            messages.append({"role": "user", "content": turn.operator})
            if turn.answer:
                messages.append({"role": "assistant", "content": turn.answer})
        return messages

    def summary(self) -> str:
        ids = self.context_ticket_ids()
        return (f"{len(self.turns)} turn(s) remembered; "
                f"{len(ids)} ticket(s) in context"
                + (f": {', '.join(ids[:5])}" if ids else ""))
