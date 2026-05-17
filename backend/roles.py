from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.schemas import QueryType


class AgentRole(str, Enum):
    INDEPENDENT_EXPERT = "Independent Expert"
    FACT_VERIFIER = "Fact Verifier"
    CODE_VERIFIER = "Code Verifier"
    DEVILS_ADVOCATE = "Devil's Advocate"
    SYNTHESIST = "Synthesis Strategist"
    ETHICIST = "Ethicist"
    CREATIVE_EXPLORER = "Creative Explorer"


class CritiqueRole(str, Enum):
    ACCURACY_AUDITOR = "Accuracy Auditor"
    LOGIC_AUDITOR = "Logic Auditor"
    COMPLETENESS_AUDITOR = "Completeness Auditor"
    CALIBRATION_AUDITOR = "Calibration Auditor"


@dataclass(frozen=True)
class RoleConfig:
    name: str
    description: str
    default_tools: tuple[str, ...] = ()


ROLE_CONFIGS = {
    AgentRole.INDEPENDENT_EXPERT: RoleConfig("Independent Expert", "Answer fully and independently."),
    AgentRole.FACT_VERIFIER: RoleConfig("Fact Verifier", "Prioritize externally verifiable factual claims.", ("web_search",)),
    AgentRole.CODE_VERIFIER: RoleConfig("Code Verifier", "Check code, algorithms, and computations.", ("code_executor", "calculator")),
    AgentRole.DEVILS_ADVOCATE: RoleConfig("Devil's Advocate", "Surface strong counterarguments and risks."),
    AgentRole.SYNTHESIST: RoleConfig("Synthesis Strategist", "Find the most coherent answer structure."),
    AgentRole.ETHICIST: RoleConfig("Ethicist", "Evaluate values, stakeholders, and tradeoffs."),
    AgentRole.CREATIVE_EXPLORER: RoleConfig("Creative Explorer", "Generate useful alternatives without losing constraints."),
}

QUERY_ROLE_MAP: dict[QueryType, list[AgentRole]] = {
    "factual": [AgentRole.FACT_VERIFIER, AgentRole.INDEPENDENT_EXPERT, AgentRole.DEVILS_ADVOCATE, AgentRole.SYNTHESIST],
    "analytical": [AgentRole.INDEPENDENT_EXPERT, AgentRole.DEVILS_ADVOCATE, AgentRole.SYNTHESIST, AgentRole.FACT_VERIFIER],
    "code": [AgentRole.CODE_VERIFIER, AgentRole.INDEPENDENT_EXPERT, AgentRole.DEVILS_ADVOCATE, AgentRole.SYNTHESIST],
    "ethics": [AgentRole.ETHICIST, AgentRole.DEVILS_ADVOCATE, AgentRole.INDEPENDENT_EXPERT, AgentRole.SYNTHESIST],
    "creative": [AgentRole.CREATIVE_EXPLORER, AgentRole.DEVILS_ADVOCATE, AgentRole.SYNTHESIST, AgentRole.INDEPENDENT_EXPERT],
    "multi_part": [AgentRole.INDEPENDENT_EXPERT, AgentRole.FACT_VERIFIER, AgentRole.DEVILS_ADVOCATE, AgentRole.SYNTHESIST],
}


def roles_for_query(query_type: QueryType, count: int) -> list[AgentRole]:
    base = QUERY_ROLE_MAP[query_type]
    return [base[index % len(base)] for index in range(count)]


def critique_roles(count: int) -> list[CritiqueRole]:
    base = [
        CritiqueRole.ACCURACY_AUDITOR,
        CritiqueRole.LOGIC_AUDITOR,
        CritiqueRole.COMPLETENESS_AUDITOR,
        CritiqueRole.CALIBRATION_AUDITOR,
    ]
    return [base[index % len(base)] for index in range(count)]


def build_system_prompt(role: str, query_type: QueryType) -> str:
    return f"""You are the {role} in Model Council.
Query type: {query_type}.

Return ONLY valid JSON with this shape:
{{
  "answer": "your answer",
  "confidence": 0.0,
  "key_claims": ["claim one", "claim two"],
  "assumptions": ["assumption"],
  "uncertainties": ["uncertainty"]
}}

Be precise and calibrated. If evidence is uncertain, say exactly what remains uncertain."""


def build_critique_prompt(critique_role: str, target_label: str, target_answer: str) -> str:
    return f"""You are the {critique_role} in Model Council.
Review only this target answer: {target_label}

Return ONLY valid JSON:
{{
  "scores": {{"accuracy": 0.0, "logic": 0.0, "completeness": 0.0, "calibration": 0.0}},
  "strengths": ["strength"],
  "weaknesses": ["weakness"],
  "flags": ["unsupported claim or risk"]
}}

Target answer:
{target_answer}
"""
