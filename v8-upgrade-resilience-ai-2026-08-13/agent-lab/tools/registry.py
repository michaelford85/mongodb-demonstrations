"""A minimal tool registry: name, description, typed parameters, callable.

Deliberately hand-rolled rather than borrowed from a framework, because the
schema is the thing being taught — it is exactly what gets serialised into the
planning prompt, and exactly what the model's reply is validated against.

Registering a tool:

    @tool("get_recent_tickets", "Newest tickets, most recent first.",
          limit=Param(int, "how many to return", default=5))
    def get_recent_tickets(limit=5):
        ...
"""


class Param:
    """One tool parameter: type, prose for the prompt, optional default/choices."""

    def __init__(self, type_, description, default=None, choices=None):
        self.type = type_
        self.description = description
        self.default = default
        self.choices = choices

    @property
    def required(self) -> bool:
        return self.default is None

    def coerce(self, value):
        """Cast a value that arrived as text (from a model or a CLI) to `type`."""
        if value is None:
            return self.default
        if self.type is int:
            value = int(value)
        elif self.type is float:
            value = float(value)
        elif self.type is bool:
            if isinstance(value, str):
                value = value.strip().lower() in {"1", "true", "yes", "on"}
            else:
                value = bool(value)
        else:
            value = str(value)
        if self.choices and value not in self.choices:
            raise ValueError(
                f"expected one of {list(self.choices)}, got {value!r}")
        return value


class Tool:
    def __init__(self, name, description, func, params):
        self.name = name
        self.description = description
        self.func = func
        self.params = params

    def signature(self) -> str:
        """One-line form used in the planning prompt."""
        parts = []
        for pname, p in self.params.items():
            hint = p.type.__name__
            if p.choices:
                hint = "|".join(str(c) for c in p.choices)
            parts.append(f"{pname}: {hint}"
                         + ("" if p.required else f" = {p.default}"))
        return f"{self.name}({', '.join(parts)})"

    def describe(self) -> str:
        lines = [f"{self.signature()}", f"    {self.description}"]
        for pname, p in self.params.items():
            lines.append(f"    - {pname}: {p.description}")
        return "\n".join(lines)

    def call(self, arguments: dict) -> dict:
        """Validate and coerce `arguments`, then invoke. Raises ValueError on
        anything the model got wrong, so the agent can report it as an
        observation rather than crashing the session."""
        arguments = arguments or {}
        unknown = set(arguments) - set(self.params)
        if unknown:
            raise ValueError(
                f"{self.name} has no parameter(s) {sorted(unknown)}; "
                f"expected {sorted(self.params)}")
        kwargs = {}
        for pname, p in self.params.items():
            raw = arguments.get(pname)
            if raw is None and p.required:
                raise ValueError(f"{self.name} requires '{pname}'")
            try:
                kwargs[pname] = p.coerce(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{self.name}.{pname}: {exc}") from exc
        return self.func(**kwargs)


REGISTRY: dict = {}


def tool(name: str, description: str, **params):
    def decorator(func):
        REGISTRY[name] = Tool(name, description, func, params)
        return func
    return decorator


def get(name: str) -> Tool:
    if name not in REGISTRY:
        raise KeyError(
            f"unknown tool '{name}'; available: {sorted(REGISTRY)}")
    return REGISTRY[name]


def all_tools() -> list:
    return [REGISTRY[n] for n in sorted(REGISTRY)]


def catalogue() -> str:
    """The full tool list as it appears in the planning prompt."""
    return "\n".join(t.describe() for t in all_tools())
