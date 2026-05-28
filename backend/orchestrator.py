from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from backend.providers import ProviderAdapter
from backend.roles import ROLE_CONFIGS, AgentRole, roles_for_query
from backend.schemas import ChatMessage, ModelRoute, OrchestrationPlan, QueryType


ORCHESTRATOR_SYSTEM = """You are an orchestration agent for Model Council.
Do not answer the query. Return only valid JSON matching the requested plan schema."""


async def classify_query(
    prompt: str,
    selected_routes: list[ModelRoute],
    orchestrator_route: ModelRoute | None,
    adapter: ProviderAdapter | None,
    tool_registry: dict[str, Any],
) -> OrchestrationPlan:
    model_ids = [route.id for route in selected_routes]
    if orchestrator_route and adapter:
        try:
            content, _, _ = await adapter.complete(
                orchestrator_route,
                [
                    ChatMessage(role="system", content=ORCHESTRATOR_SYSTEM),
                    ChatMessage(role="user", content=_build_prompt(prompt, model_ids)),
                ],
            )
            data = json.loads(_extract_json(content))
            plan = OrchestrationPlan.model_validate(data)
            return _normalize_plan(plan, model_ids, tool_registry)
        except (json.JSONDecodeError, ValidationError, KeyError, ValueError):
            pass
        except Exception:
            pass
    return fallback_plan(prompt, model_ids, tool_registry)


def fallback_plan(prompt: str, model_ids: list[str], tool_registry: dict[str, Any]) -> OrchestrationPlan:
    query_type = _heuristic_query_type(prompt)
    roles = _assign_roles(query_type, model_ids)
    return OrchestrationPlan(
        query_type=query_type,
        is_multi_part=False,
        sub_questions=[],
        role_assignments=roles,
        tool_assignments=_assign_tools(roles, tool_registry),
        decomposition_rationale="Fallback heuristic plan; no decomposition applied.",
        orchestration_status="fallback",
    )


def _build_prompt(prompt: str, model_ids: list[str]) -> str:
    return f"""Query: {prompt}

Available models: {model_ids}

Return an OrchestrationPlan JSON object with:
- query_type: one of [factual, analytical, code, ethics, creative, multi_part]
- is_multi_part: boolean
- sub_questions: list of strings
- role_assignments: object mapping model_id to role name
- tool_assignments: object mapping model_id to list of tool names
- decomposition_rationale: one sentence"""


def _normalize_plan(plan: OrchestrationPlan, model_ids: list[str], tool_registry: dict[str, Any]) -> OrchestrationPlan:
    roles = plan.role_assignments or _assign_roles(plan.query_type, model_ids)
    roles = {model_id: roles.get(model_id) or "Independent Expert" for model_id in model_ids}
    return plan.model_copy(
        update={
            "role_assignments": roles,
            "tool_assignments": _assign_tools(roles, tool_registry),
            "sub_questions": plan.sub_questions[:5],
            "is_multi_part": bool(plan.sub_questions) if plan.query_type == "multi_part" else False,
        }
    )


def _assign_roles(query_type: QueryType, model_ids: list[str]) -> dict[str, str]:
    roles = roles_for_query(query_type, len(model_ids))
    return {model_id: roles[index].value for index, model_id in enumerate(model_ids)}


def _assign_tools(role_assignments: dict[str, str], tool_registry: dict[str, Any]) -> dict[str, list[str]]:
    by_name = {config.name: config.default_tools for config in ROLE_CONFIGS.values()}
    return {
        model_id: [tool for tool in by_name.get(role, ()) if tool in tool_registry]
        for model_id, role in role_assignments.items()
    }


def _heuristic_query_type(prompt: str) -> QueryType:
    lowered = prompt.lower()
    if any(word in lowered for word in ["code", "python", "javascript", "bug", "function", "traceback"]):
        return "code"
    if any(word in lowered for word in ["ethical", "ethics", "moral", "should society"]):
        return "ethics"
    if any(word in lowered for word in ["write a story", "brainstorm", "creative", "poem"]):
        return "creative"
    if any(word in lowered for word in ["who", "when", "where", "latest", "current", "source"]):
        return "factual"
    return "analytical"


def _extract_json(content: str) -> str:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)
