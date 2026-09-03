"""CLI for the support agent.

    python app/main.py                          interactive session
    python app/main.py --ask "what is urgent?"  one turn, then exit
    python app/main.py --script scripts/triage.txt
    python app/main.py --tools                  print the tool catalogue

Session commands: /memory, /tools, /trace, /reset, /quit
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import agent as agent_mod  # noqa: E402
import config  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import tools  # noqa: E402

BANNER = """Support agent lab
  model      {model}
  namespace  {namespace}
  search     {search}
  max steps  {steps} per turn, memory {turns} turns
Type a question, or /help. Ctrl-D to exit."""

HELP = """  /tools    the tool catalogue exactly as the model sees it
  /memory   what short-term memory currently holds
  /trace    toggle the plan/act/observe trace
  /reset    forget the conversation
  /quit     exit"""


def _banner() -> str:
    return BANNER.format(
        model=llm.describe(),
        namespace=config.namespace(),
        search="Atlas Vector Search" if config.USE_VECTOR_SEARCH
        else "keyword scan (set USE_VECTOR_SEARCH=true for vector search)",
        steps=config.MAX_STEPS,
        turns=config.MEMORY_TURNS,
    )


def _check_data() -> None:
    try:
        count = config.get_tickets().count_documents({}, limit=1)
    except Exception as exc:  # noqa: BLE001 — surface connection problems plainly
        raise SystemExit(f"Could not reach MongoDB: {exc}")
    if not count:
        raise SystemExit(
            f"No tickets in {config.namespace()}. Run:\n"
            "  python data/build_tickets.py\n"
            "  python app/seed.py")


def _command(line: str, ag: agent_mod.Agent) -> bool:
    """Handle a /command. Returns False when the session should end."""
    cmd = line.split()[0].lower()
    if cmd in ("/quit", "/exit"):
        return False
    if cmd == "/help":
        print(HELP)
    elif cmd == "/tools":
        print(tools.catalogue())
    elif cmd == "/memory":
        print("  " + ag.session.summary())
        for turn in ag.session.turns:
            calls = ", ".join(s["tool"] for s in turn.steps if "tool" in s)
            print(f"  - {turn.operator!r} -> {calls or 'no tool'}")
    elif cmd == "/trace":
        config.SHOW_TRACE = not config.SHOW_TRACE
        print(f"  trace {'on' if config.SHOW_TRACE else 'off'}")
    elif cmd == "/reset":
        ag.session.clear()
        print("  memory cleared")
    else:
        print(f"  unknown command {cmd}; try /help")
    return True


def _turn(ag: agent_mod.Agent, question: str) -> None:
    print(f"\n> {question}")
    answer = ag.ask(question)
    print(f"\n{answer}\n")


def run_script(ag: agent_mod.Agent, path: Path) -> None:
    """Replay a scripted conversation. Blank lines and '#' are ignored."""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/"):
            _command(line, ag)
            continue
        _turn(ag, line)


def interactive(ag: agent_mod.Agent) -> None:
    print(_banner())
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line.startswith("/"):
            if not _command(line, ag):
                return
            continue
        answer = ag.ask(line)
        print(f"\n{answer}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Support agent lab CLI.")
    parser.add_argument("--ask", help="run one question and exit")
    parser.add_argument("--script", type=Path,
                        help="replay a file of questions, one per line")
    parser.add_argument("--tools", action="store_true",
                        help="print the tool catalogue and exit")
    parser.add_argument("--no-trace", action="store_true",
                        help="hide the plan/act/observe trace")
    args = parser.parse_args()

    if args.tools:
        print(tools.catalogue())
        return
    if args.no_trace:
        config.SHOW_TRACE = False

    _check_data()
    ag = agent_mod.Agent(memory.Session())

    if args.ask:
        _turn(ag, args.ask)
    elif args.script:
        if not args.script.exists():
            raise SystemExit(f"{args.script} not found")
        print(_banner())
        run_script(ag, args.script)
    else:
        interactive(ag)


if __name__ == "__main__":
    main()
