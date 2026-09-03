"""Small terminal formatting helpers so both demos print the same way."""
import json

from bson.binary import Binary


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def section(title: str) -> None:
    print()
    print(f"-- {title} " + "-" * max(0, 74 - len(title)))


def bindata_repr(value) -> str:
    """Render a BinData UUID the way mongosh would, strings unchanged."""
    if isinstance(value, Binary):
        return f"UUID('{value.as_uuid()}')"
    return str(value)


def pipeline_block(pipeline: list) -> None:
    for line in json.dumps(pipeline, indent=2, default=str).splitlines():
        print(f"  {line}")


def rows(docs: list, columns: list) -> None:
    if not docs:
        print("  (no documents)")
        return
    widths = [
        max(len(col), *(len(str(d.get(col, ""))) for d in docs)) for col in columns
    ]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*columns))
    print(fmt.format(*("-" * w for w in widths)))
    for doc in docs:
        print(fmt.format(*(str(doc.get(col, "")) for col in columns)))
