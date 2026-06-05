from types import SimpleNamespace

import pytest

from backend.tools import (
    CalculatorTool,
    WebSearchTool,
    build_tool_registry,
    inject_tool_results,
)


@pytest.mark.asyncio
async def test_calculator_evaluates_expression():
    result = await CalculatorTool().run({"expression": "2 + 3 * 4"})
    assert result.success is True
    assert result.result == "14"


@pytest.mark.asyncio
async def test_calculator_rejects_unsafe_expression():
    result = await CalculatorTool().run({"expression": "__import__('os').system('echo hi')"})
    assert result.success is False


@pytest.mark.asyncio
async def test_web_search_without_key_fails_gracefully():
    tool = WebSearchTool(provider="tavily", api_key=None)
    result = await tool.run({"query": "anything"})
    assert result.success is False
    assert "no API key" in (result.error or "")


def test_registry_excludes_disabled_tools_by_default():
    settings = SimpleNamespace(
        tool_code_executor_enabled=False,
        tool_web_search_enabled=False,
    )
    registry = build_tool_registry(settings)
    assert "calculator" in registry
    assert "code_executor" not in registry
    assert "web_search" not in registry


def test_registry_wires_web_search_provider_and_key():
    settings = SimpleNamespace(
        tool_code_executor_enabled=False,
        tool_web_search_enabled=True,
        tool_web_search_provider="serper",
        tavily_api_key=None,
        serper_api_key="serper-key",
        brave_search_api_key=None,
    )
    registry = build_tool_registry(settings)
    tool = registry["web_search"]
    assert isinstance(tool, WebSearchTool)
    assert tool.provider == "serper"
    assert tool.api_key == "serper-key"


@pytest.mark.asyncio
async def test_inject_tool_results_runs_json_tool_call():
    content = 'I will compute. TOOL_CALL: {"tool": "calculator", "expression": "6*7"}'
    new_content, results = await inject_tool_results(content, {"calculator": CalculatorTool()})
    assert len(results) == 1
    assert results[0].success is True
    assert "TOOL_RESULT: calculator => 42" in new_content
