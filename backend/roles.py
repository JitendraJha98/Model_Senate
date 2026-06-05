from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from backend.schemas import AgentOpinion, QueryType


class AgentRole(str, Enum):
    INDEPENDENT_EXPERT = "Independent Expert"
    DEVIL_ADVOCATE = "Devil's Advocate"
    STEELMAN = "Steelman"
    FACT_VERIFIER = "Fact Verifier"
    CODE_VERIFIER = "Code Verifier"
    DOMAIN_SPECIALIST = "Domain Specialist"
    SYNTHESIZER = "Synthesizer"


class CritiqueRole(str, Enum):
    CHALLENGER = "Challenger"
    STEELMAN_REVIEWER = "Steelman Reviewer"
    CALIBRATION_AUDITOR = "Calibration Auditor"


@dataclass(frozen=True)
class RoleConfig:
    name: str
    description: str
    default_tools: tuple[str, ...] = field(default_factory=tuple)


ROLE_CONFIGS: dict[AgentRole, RoleConfig] = {
    AgentRole.INDEPENDENT_EXPERT: RoleConfig(
        "Independent Expert",
        "Answer fully and independently. Be precise and calibrate confidence explicitly.",
    ),
    AgentRole.DEVIL_ADVOCATE: RoleConfig(
        "Devil's Advocate",
        "Surface the strongest counterargument to the expected answer.",
    ),
    AgentRole.STEELMAN: RoleConfig(
        "Steelman",
        "Build the most charitable version of each competing view.",
    ),
    AgentRole.FACT_VERIFIER: RoleConfig(
        "Fact Verifier",
        "Ground-truth factual claims with verifiable sources.",
        default_tools=("web_search",),
    ),
    AgentRole.CODE_VERIFIER: RoleConfig(
        "Code Verifier",
        "Test computational and code claims by running them.",
        default_tools=("code_executor", "calculator"),
    ),
    AgentRole.DOMAIN_SPECIALIST: RoleConfig(
        "Domain Specialist",
        "Provide deep domain-specific expertise.",
    ),
    AgentRole.SYNTHESIZER: RoleConfig(
        "Synthesizer",
        "Unify all evidence into a coherent final answer.",
    ),
}

# Spec table: query_type → roles by model count
# Lists cycle for model counts > len(list)
QUERY_ROLE_MAP: dict[QueryType, list[AgentRole]] = {
    "factual": [
        AgentRole.FACT_VERIFIER,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.DEVIL_ADVOCATE,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.FACT_VERIFIER,
        AgentRole.DOMAIN_SPECIALIST,
    ],
    "analytical": [
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.DEVIL_ADVOCATE,
        AgentRole.STEELMAN,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.STEELMAN,
        AgentRole.DEVIL_ADVOCATE,
    ],
    "code": [
        AgentRole.CODE_VERIFIER,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.DEVIL_ADVOCATE,
        AgentRole.CODE_VERIFIER,
        AgentRole.DOMAIN_SPECIALIST,
        AgentRole.CODE_VERIFIER,
    ],
    "ethics": [
        AgentRole.STEELMAN,
        AgentRole.DEVIL_ADVOCATE,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.STEELMAN,
        AgentRole.DEVIL_ADVOCATE,
        AgentRole.STEELMAN,
    ],
    "creative": [
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.STEELMAN,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.STEELMAN,
        AgentRole.INDEPENDENT_EXPERT,
    ],
    "multi_part": [
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.FACT_VERIFIER,
        AgentRole.DEVIL_ADVOCATE,
        AgentRole.STEELMAN,
        AgentRole.INDEPENDENT_EXPERT,
        AgentRole.FACT_VERIFIER,
    ],
}


def roles_for_query(query_type: QueryType, count: int) -> list[AgentRole]:
    base = QUERY_ROLE_MAP[query_type]
    return [base[i % len(base)] for i in range(count)]


def critique_roles(count: int) -> list[CritiqueRole]:
    base = [CritiqueRole.CHALLENGER, CritiqueRole.STEELMAN_REVIEWER, CritiqueRole.CALIBRATION_AUDITOR]
    return [base[i % len(base)] for i in range(count)]


_SYSTEM_PROMPTS: dict[AgentRole, str] = {
    AgentRole.INDEPENDENT_EXPERT: """\
You are an expert council member in Model Council.
Answer the query fully and independently. You have not seen other models' answers.
Be precise. Calibrate your confidence explicitly — state what you are certain of and what you are not.
Name every assumption you are making. If the answer is genuinely uncertain, say so with specificity.\
""",

    AgentRole.DEVIL_ADVOCATE: """\
You are the Devil's Advocate in Model Council.
Your role is to surface the strongest counterargument to the expected or conventional answer.
Start by identifying what the conventional answer is, then argue forcefully against it.
Do not be contrarian for its own sake — find the genuinely strongest opposing case.
You are not trying to be right. You are trying to make the council think harder.\
""",

    AgentRole.STEELMAN: """\
You are the Steelman agent in Model Council.
Your role is to identify the 2–3 major competing views on this question and build the strongest,
most charitable version of each. Do not argue for one view over another.
Make each view as compelling as possible. A reader should feel that each view is reasonable.\
""",

    AgentRole.FACT_VERIFIER: """\
You are the Fact Verifier in Model Council.
For every factual claim in your answer, you must either cite a verifiable source or mark the claim as unverified.
Use your web search tool to check key claims before including them.
Report tool results explicitly. Flag any claim you could not verify.\
""",

    AgentRole.CODE_VERIFIER: """\
You are the Code Verifier in Model Council.
For any code or computation in your answer, run it using your code execution tool before presenting it.
Report the actual output. Do not claim code works without running it.
If execution reveals an error, fix it and re-run. Report the final working version only.\
""",

    AgentRole.DOMAIN_SPECIALIST: """\
You are the Domain Specialist in Model Council.
Provide deep, authoritative expertise for this specific domain.
Reference established principles, known edge cases, and domain-specific nuance that a generalist would miss.
Be explicit about the limits of what can be known in this domain.\
""",

    AgentRole.SYNTHESIZER: """\
You are the elected Synthesizer in Model Council.
Your role is to integrate all council evidence into a final coherent answer.
Do not simply average opinions — find the truth supported by the best evidence.
Be explicit about consensus, dissent, and what remains unresolved.\
""",
}


def build_system_prompt(role: str, query_type: QueryType, domain: str | None = None) -> str:
    try:
        agent_role = AgentRole(role)
        base = _SYSTEM_PROMPTS[agent_role]
    except ValueError:
        base = f"You are the {role} in Model Council. Answer the query fully and precisely."

    type_note = {
        "factual": "Prioritize verifiable facts and cite sources where possible.",
        "analytical": "Prioritize clear reasoning chains and explicit weighing of evidence.",
        "code": "Prioritize correctness, edge cases, and running/verifying code.",
        "ethics": "Prioritize identifying stakeholders, competing values, and trade-offs.",
        "creative": "Prioritize originality and concrete specificity without losing constraints.",
        "multi_part": "Address each component of the query distinctly.",
    }.get(query_type, "")

    domain_note = f"\nDomain context: {domain}." if domain else ""

    structured_instruction = """

Provide your prose response first, then end with a COUNCIL_OUTPUT: JSON block:

COUNCIL_OUTPUT:
{
  "answer_summary": "one sentence summary of your answer",
  "confidence": 0.0,
  "confidence_rationale": "why you chose this confidence level",
  "key_claims": [
    {"text": "claim text", "verifiable": true, "source": "URL or null", "verified": false}
  ],
  "uncertainties": ["things you explicitly do not know"],
  "tool_results": []
}

Be precise and calibrated. If evidence is uncertain, say so with specificity."""

    return f"{base}\n\nQuery type: {query_type}. {type_note}{domain_note}{structured_instruction}"


def build_critique_prompt(
    critique_role: str,
    reviewer: AgentOpinion,
    targets: list[AgentOpinion],
    anonymized_map: dict[str, str],
) -> str:
    """Build a critique prompt for one reviewer to score ALL target models."""
    # Build the reversed map: model_id → label (e.g. "Agent A")
    label_for = {model_id: label for label, model_id in anonymized_map.items()}

    role_instructions = {
        CritiqueRole.CHALLENGER.value: (
            "Identify factual errors, unsupported claims, and logical fallacies in each response. "
            "Be rigorous — your job is to find what is wrong, not to be fair."
        ),
        CritiqueRole.STEELMAN_REVIEWER.value: (
            "Find what each answer got most right. Build the strongest case for each response "
            "as if you were defending it. Identify its most defensible claims."
        ),
        CritiqueRole.CALIBRATION_AUDITOR.value: (
            "Compare the stated confidence of each answer against the actual accuracy of its claims. "
            "Score whether confidence was appropriate — overconfident answers should score low."
        ),
    }.get(critique_role, "Evaluate the accuracy, logic, completeness, and calibration of each response.")

    targets_text = ""
    for target in targets:
        label = label_for.get(target.model_id, target.model_id)
        targets_text += f"\n### {label}\n{target.content}\n"

    n = len(targets)
    rank_note = f"Assign overall_rank from 1 (best) to {n} (worst). Each rank must be unique."

    label_list = [label_for.get(t.model_id, t.model_id) for t in targets]
    keys_example = {label: {
        "factual_accuracy_score": 0.0,
        "logical_validity_score": 0.0,
        "completeness_score": 0.0,
        "calibration_score": 0.0,
        "overall_rank": 1,
        "strengths": ["..."],
        "weaknesses": ["..."],
        "corrective_additions": ["..."],
    } for label in label_list}

    schema_example = json.dumps({"reviews": keys_example}, indent=2)

    return f"""You are the {critique_role} in Model Council.

Your task: {role_instructions}

{rank_note}

Score each response (0.0–1.0):
- factual_accuracy_score: Are the claims correct?
- logical_validity_score: Is the reasoning sound?
- completeness_score: Was anything important missed?
- calibration_score: Did the stated confidence match actual accuracy?

Return ONLY valid JSON matching this schema:
{schema_example}

Responses to review:
{targets_text}
"""
