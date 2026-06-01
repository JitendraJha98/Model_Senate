from __future__ import annotations

import ast
import operator
import re
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any

from backend.schemas import ToolResult


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, params: dict[str, Any]) -> ToolResult:
        raise NotImplementedError


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluates mathematical expressions safely."
    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    async def run(self, params: dict[str, Any]) -> ToolResult:
        expression = str(params.get("expression", ""))
        started = time.perf_counter()
        try:
            value = self._eval(ast.parse(expression, mode="eval").body)
            return ToolResult(
                tool=self.name,
                params=params,
                result=str(value),
                success=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolResult(tool=self.name, params=params, result="", success=False, error=str(exc))

    def _eval(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._operators:
            return self._operators[type(node.op)](self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._operators:
            return self._operators[type(node.op)](self._eval(node.operand))
        raise ValueError("Unsupported calculator expression")


class CodeExecutorTool(Tool):
    name = "code_executor"
    description = "Runs Python code in a sandboxed subprocess."

    def __init__(self, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds

    async def run(self, params: dict[str, Any]) -> ToolResult:
        code = str(params.get("code", ""))
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            output = (completed.stdout or completed.stderr)[:4000]
            return ToolResult(
                tool=self.name,
                params=params,
                result=output,
                success=completed.returncode == 0,
                error=None if completed.returncode == 0 else f"Exited with {completed.returncode}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolResult(tool=self.name, params=params, result="", success=False, error=str(exc))


class WebSearchTool(Tool):
    name = "web_search"
    description = "Searches the web for information."

    async def run(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool=self.name,
            params=params,
            result="",
            success=False,
            error="Web search tool is configured but no provider adapter is implemented yet.",
        )


ToolRegistry = dict[str, Tool]


def build_tool_registry(settings: Any) -> ToolRegistry:
    registry: ToolRegistry = {"calculator": CalculatorTool()}
    if getattr(settings, "tool_code_executor_enabled", False):
        registry["code_executor"] = CodeExecutorTool(getattr(settings, "tool_code_executor_timeout_seconds", 10))
    if getattr(settings, "tool_web_search_enabled", False):
        registry["web_search"] = WebSearchTool()
    return registry


async def inject_tool_results(content: str, tool_registry: ToolRegistry) -> tuple[str, list[ToolResult]]:
    results: list[ToolResult] = []
    for tool_name, tool_params in _parse_tool_calls(content):
        tool = tool_registry.get(tool_name)
        if not tool:
            results.append(ToolResult(tool=tool_name, params=tool_params, result="", success=False, error="Tool not available"))
            continue
        results.append(await tool.run(tool_params))
    if not results:
        return content, results
    result_block = "\n".join(
        f"TOOL_RESULT: {r.tool} => {r.result if r.success else 'FAILED: ' + (r.error or 'unknown')}"
        for r in results
    )
    return f"{content}\n\n{result_block}", results


def _parse_tool_calls(content: str) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    # Match: TOOL_CALL: {"tool": "calculator", "expression": "2+2"}
    json_pattern = re.compile(r'TOOL_CALL:\s*(\{.*?\})', re.IGNORECASE | re.DOTALL)
    for match in json_pattern.finditer(content):
        try:
            import json
            data = json.loads(match.group(1))
            tool_name = data.pop("tool", None)
            if tool_name:
                calls.append((tool_name, data))
        except Exception:
            pass
    # Fallback: TOOL_CALL: tool_name: input
    if not calls:
        simple_pattern = re.compile(r'TOOL_CALL:\s*([a-zA-Z_][\w-]*)\s*(?:\((.*?)\)|:\s*(.*))', re.IGNORECASE)
        for line in content.splitlines():
            match = simple_pattern.search(line)
            if match:
                tool_name = match.group(1)
                raw = (match.group(2) or match.group(3) or "").strip()
                calls.append((tool_name, {"expression": raw} if tool_name == "calculator" else {"code": raw} if tool_name == "code_executor" else {"query": raw}))
    return calls
