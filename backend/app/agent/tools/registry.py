"""
agent/tools/registry.py
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any
import inspect

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    name:         str
    description:  str
    input_schema: dict

    @abstractmethod
    async def run(self, context: Any, db: Any, **kwargs) -> dict: ...

    @staticmethod
    def ok(data: Any) -> dict:
        return {"success": True, "data": data, "error": None}

    @staticmethod
    def err(message: str, data: Any = None) -> dict:
        return {"success": False, "data": data, "error": message}


def _try_register(registry: dict, module_path: str, class_name: str) -> None:
    try:
        import importlib
        mod  = importlib.import_module(module_path)
        tool = getattr(mod, class_name)()
        registry[tool.name] = tool
    except Exception as e:
        logger.warning("Tool %s.%s skipped: %s", module_path, class_name, e)


def _build_registry() -> dict[str, BaseTool]:
    r: dict[str, BaseTool] = {}
    _try_register(r, "app.agent.tools.case_status",    "CaseStatusTool")
    _try_register(r, "app.agent.tools.hearing_history","HearingHistoryTool")
    _try_register(r, "app.agent.tools.cause_list",     "CauseListTool")
    _try_register(r, "app.agent.tools.roster",         "RosterTool")
    _try_register(r, "app.agent.tools.drafting",       "DraftDocumentTool")
    _try_register(r, "app.agent.tools.judgement_search",   "JudgmentSearchTool")
    _try_register(r, "app.agent.tools.search_resources",   "SearchResourcesTool")
    _try_register(r, "app.agent.tools.web_search",         "WebSearchTool")
    _try_register(r, "app.agent.tools.advocate_cause_list", "AdvocateCauseListTool")
    _try_register(r, "app.agent.tools.calendar",           "CreateCalendarEventTool")
    _try_register(r, "app.agent.tools.calendar",           "GetCalendarEventsTool")
    _try_register(r, "app.agent.tools.calendar",           "DeleteCalendarEventTool")
    logger.info("Agent tools ready: %s", list(r.keys()))
    return r


TOOL_REGISTRY: dict[str, BaseTool] = _build_registry()


def _normalize_input_schema(schema: dict | None) -> dict:
    s = dict(schema or {})
    # Bedrock requires inputSchema.json.type to be present and "object".
    if s.get("type") != "object":
        s["type"] = "object"
    # Ensure keys exist for consistency.
    if "properties" not in s or not isinstance(s.get("properties"), dict):
        s["properties"] = {}
    if "required" in s and not isinstance(s.get("required"), list):
        s["required"] = []
    return s


def get_bedrock_tools() -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": {"json": _normalize_input_schema(t.input_schema)},
        }
        for t in TOOL_REGISTRY.values()
    ]


async def dispatch_tool(
    tool_name: str,
    tool_inputs: dict | None = None,
    context: Any = None,
    db: Any = None,
    **kwargs: Any,
) -> dict:
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        return {"success": False, "data": None, "error": f"Tool '{tool_name}' not available"}
    inputs = tool_inputs
    if inputs is None:
        inputs = kwargs.get("tool_input", {})  # backward compatibility
    if inputs is None:
        inputs = {}
    try:
        sig = inspect.signature(tool.run)
        param_names = set(sig.parameters.keys())

        # Newer tools: run(context=..., db=..., **kwargs)
        if "db" in param_names:
            return await tool.run(context=context, db=db, **inputs)

        # Older tools: run(inputs, context)
        if "inputs" in param_names:
            return await tool.run(inputs=inputs, context=context)

        # Generic fallback
        return await tool.run(context=context, **inputs)
    except Exception as e:
        logger.exception("Tool %s crashed: %s", tool_name, e)
        return {"success": False, "data": None, "error": str(e)}
