"""Tool surface for the support agent.

Importing this package registers every tool, so the agent only ever needs:

    import tools
    tools.catalogue()          # the prompt-facing tool list
    tools.get(name).call(args) # validated dispatch
"""
from . import tickets  # noqa: F401 — imported for its registration side effect
from .registry import Param, Tool, all_tools, catalogue, get, tool

__all__ = ["Param", "Tool", "all_tools", "catalogue", "get", "tool"]
