"""Tool registry: which tools are writes, which need a checkpoint, what they cost."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolInfo:
    name: str
    write: bool = False
    requires_checkpoint: bool = False
    cost_usd: float = 0.0


def _as_bool(entry: dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key in entry:
            return bool(entry[key])
    return default


def _cost(entry: dict[str, Any]) -> float:
    for key in ("cost_usd_per_call", "cost_usd", "cost_per_call_usd"):
        if key in entry:
            return float(entry[key])
    return 0.0


def parse_tools(raw: Any) -> dict[str, ToolInfo]:
    """Accept {"tools": [...]}, a bare list, or a dict keyed by tool name."""
    if isinstance(raw, dict) and isinstance(raw.get("tools"), (list, dict)):
        raw = raw["tools"]
    items: list[tuple[str, dict[str, Any]]]
    if isinstance(raw, list):
        items = [(e["name"], e) for e in raw]
    elif isinstance(raw, dict):
        items = [(k, v) for k, v in raw.items() if isinstance(v, dict)]
    else:
        raise TypeError("unrecognised tools.json shape")
    tools: dict[str, ToolInfo] = {}
    for name, entry in items:
        write = _as_bool(entry, "write", "is_write")
        tools[name] = ToolInfo(
            name=name,
            write=write,
            requires_checkpoint=_as_bool(entry, "requires_checkpoint", "checkpoint", default=write),
            cost_usd=_cost(entry),
        )
    return tools