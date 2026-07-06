"""MCP server exposing the Council as a `consult_council` tool.

Lets agents (Claude Code, Codex, …) convene the multi-model council for high-stakes
questions and get back a synthesized answer with a confidence grade, consensus, and
dissent. The `mcp` SDK is an optional extra (`pip install model-senate[mcp]`); the core
`consult_council` coroutine has no such dependency so it stays unit-testable.

Run:  python -m backend.mcp_server   (stdio transport)
"""

from __future__ import annotations

from backend.facade import council_answer
from backend.schemas import CouncilRequest


async def consult_council(question: str, model_ids: list[str] | None = None) -> dict:
    """Run the Council on a question and return a compact, agent-friendly result."""
    import backend.main as app  # reuse the process-wide configured services

    ids = model_ids or [route.id for route in app.routes if not route.missing_key]
    if len(ids) < app.settings.council_min_models:
        return {"error": f"Need at least {app.settings.council_min_models} available models; {len(ids)} configured"}

    run = await app.council_service.run(CouncilRequest(prompt=question, selected_model_ids=ids))
    return {
        "answer": council_answer(run),
        "confidence_grade": run.confidence_grade,
        "consensus": run.synthesis.consensus_points if run.synthesis else [],
        "dissent": run.synthesis.dissent_points if run.synthesis else [],
        "unresolved": run.synthesis.unresolved_conflicts if run.synthesis else [],
        "status": run.status,
        "run_id": run.id,
    }


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("model-council")

    @server.tool()
    async def consult_council_tool(question: str) -> dict:
        """Convene a multi-model council on a high-stakes question. Returns a synthesized
        answer with a confidence grade (A–F), consensus points, and dissent."""
        return await consult_council(question)

    server.run()


if __name__ == "__main__":
    main()
