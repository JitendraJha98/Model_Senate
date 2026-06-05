from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from backend.providers import ProviderAdapter
from backend.roles import ROLE_CONFIGS, AgentRole, roles_for_query
from backend.schemas import ChatMessage, ModelRoute, OrchestrationPlan, QueryType, SubQuestion


ORCHESTRATOR_SYSTEM = """\
You are an orchestration agent for Model Council, a multi-model deliberation system.
Your job is to analyze the user's query and return a structured JSON orchestration plan.
Do not answer the query. Only produce the plan.

Return ONLY valid JSON matching the provided schema. No prose. No markdown. Raw JSON only.

Query type taxonomy:
- factual: has a ground-truth answer, verifiable with sources
- analytical: requires reasoning, weighing evidence, drawing conclusions
- code: involves writing, debugging, or explaining code or computation
- ethics: involves value judgements, moral reasoning, competing principles
- creative: open-ended, no single correct answer
- multi_part: contains multiple distinct questions benefiting from independent treatment\
"""


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
            plan = _parse_plan(data, model_ids, tool_registry)
            return plan
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
        decomposition_rationale="Fallback heuristic plan; orchestrator call failed.",
        orchestration_status="fallback",
    )


def _build_prompt(prompt: str, model_ids: list[str]) -> str:
    return f"""\
Query: {prompt}

Available models: {model_ids}

Return an OrchestrationPlan JSON object with:
- query_type: one of [factual, analytical, code, ethics, creative, multi_part]
- is_multi_part: boolean
- sub_questions: list of objects with "question" and "query_type" keys \
(empty if not multi_part, 2-5 items if multi_part)
- role_assignments: dict mapping model_id to role name
- tool_assignments: dict mapping model_id to list of tool names
- decomposition_rationale: one sentence explaining why decomposition was/was not applied\
"""


def _parse_plan(data: dict, model_ids: list[str], tool_registry: dict[str, Any]) -> OrchestrationPlan:
    query_type: QueryType = data.get("query_type", "analytical")
    if query_type not in ("factual", "analytical", "code", "ethics", "creative", "multi_part"):
        query_type = "analytical"

    raw_sub = data.get("sub_questions") or []
    sub_questions: list[SubQuestion] = []
    for item in raw_sub[:5]:
        if isinstance(item, dict) and "question" in item:
            sq_type = item.get("query_type", "analytical")
            if sq_type not in ("factual", "analytical", "code", "ethics", "creative", "multi_part"):
                sq_type = "analytical"
            sub_questions.append(SubQuestion(question=item["question"], query_type=sq_type))
        elif isinstance(item, str):
            sub_questions.append(SubQuestion(question=item, query_type="analytical"))

    is_multi = bool(sub_questions) and query_type == "multi_part"

    raw_roles: dict[str, str] = data.get("role_assignments") or {}
    roles = {mid: raw_roles.get(mid, "Independent Expert") for mid in model_ids}

    return OrchestrationPlan(
        query_type=query_type,
        is_multi_part=is_multi,
        sub_questions=sub_questions,
        role_assignments=roles,
        tool_assignments=_assign_tools(roles, tool_registry),
        decomposition_rationale=str(data.get("decomposition_rationale", "")),
        orchestration_status="success",
    )


def _assign_roles(query_type: QueryType, model_ids: list[str]) -> dict[str, str]:
    roles = roles_for_query(query_type, len(model_ids))
    return {mid: roles[i].value for i, mid in enumerate(model_ids)}


def _assign_tools(role_assignments: dict[str, str], tool_registry: dict[str, Any]) -> dict[str, list[str]]:
    by_name = {config.name: config.default_tools for config in ROLE_CONFIGS.values()}
    return {
        mid: [t for t in by_name.get(role, ()) if t in tool_registry]
        for mid, role in role_assignments.items()
    }


def _heuristic_query_type(prompt: str) -> QueryType:
    lowered = prompt.lower()
    if any(w in lowered for w in ["code", "python", "javascript", "bug", "function", "traceback", "compile"]):
        return "code"
    if any(w in lowered for w in ["ethical", "ethics", "moral", "should society", "is it right"]):
        return "ethics"
    if any(w in lowered for w in ["write a story", "brainstorm", "creative", "poem", "imagine"]):
        return "creative"
    if any(w in lowered for w in ["who", "when", "where", "latest", "current", "source", "cite"]):
        return "factual"
    return "analytical"


def _extract_json(content: str) -> str:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)
