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

    @abstractmethod
    async def run(self, tool_input: str) -> ToolResult:
        raise NotImplementedError


class CalculatorTool(Tool):
    name = "calculator"
    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    async def run(self, tool_input: str) -> ToolResult:
        started = time.perf_counter()
        try:
            value = self._eval(ast.parse(tool_input, mode="eval").body)
            return ToolResult(
                tool_name=self.name,
                success=True,
                input=tool_input,
                output=str(value),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, input=tool_input, error=str(exc))

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

    def __init__(self, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds

    async def run(self, tool_input: str) -> ToolResult:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                ["python", "-c", tool_input],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            return ToolResult(
                tool_name=self.name,
                success=completed.returncode == 0,
                input=tool_input,
                output=(completed.stdout or completed.stderr)[:4000],
                error=None if completed.returncode == 0 else f"Exited with {completed.returncode}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, input=tool_input, error=str(exc))


class WebSearchTool(Tool):
    name = "web_search"

    async def run(self, tool_input: str) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            success=False,
            input=tool_input,
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
    for tool_name, tool_input in _tool_calls(content):
        tool = tool_registry.get(tool_name)
        if not tool:
            results.append(ToolResult(tool_name=tool_name, success=False, input=tool_input, error="Tool is not available"))
            continue
        results.append(await tool.run(tool_input))
    if not results:
        return content, results
    result_block = "\n".join(
        f"- {result.tool_name}({result.input}) => "
        f"{result.output if result.success else 'FAILED: ' + (result.error or 'unknown error')}"
        for result in results
    )
    return f"{content}\n\nTool results:\n{result_block}", results


def _tool_calls(content: str) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    pattern = re.compile(r"TOOL_CALL:\s*([a-zA-Z_][\w-]*)\s*(?:\((.*?)\)|:\s*(.*))", re.IGNORECASE)
    for line in content.splitlines():
        match = pattern.search(line)
        if match:
            calls.append((match.group(1), (match.group(2) or match.group(3) or "").strip()))
    return calls
