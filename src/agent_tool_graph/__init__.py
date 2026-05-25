"""
agent-tool-graph: Declarative tool prerequisites — define which tools must run before others.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class CycleError(ValueError):
    """Raised when a dependency cycle is detected."""
    pass


class MissingTool(KeyError):
    """Raised when a referenced tool is not registered."""
    pass


@dataclass
class ToolNode:
    name: str
    description: str = ""
    requires: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolGraph:
    """
    Declarative dependency graph for agent tools.

    Register tools with their prerequisites, then query execution order,
    detect missing dependencies, and find cycles before running anything.

    Usage::

        g = ToolGraph()
        g.add("fetch_page")
        g.add("parse_html", requires=["fetch_page"])
        g.add("extract_data", requires=["parse_html"])

        order = g.execution_order("extract_data")
        # ["fetch_page", "parse_html", "extract_data"]
    """

    def __init__(self) -> None:
        self._nodes: dict[str, ToolNode] = {}

    def add(
        self,
        name: str,
        requires: Optional[list[str]] = None,
        description: str = "",
        **metadata: Any,
    ) -> "ToolGraph":
        self._nodes[name] = ToolNode(
            name=name,
            description=description,
            requires=requires or [],
            metadata=metadata,
        )
        return self

    def register(self, requires: Optional[list[str]] = None, description: str = "") -> Any:
        """Decorator: @graph.register(requires=['other_tool'])."""
        def decorator(fn: Any) -> Any:
            self.add(fn.__name__, requires=requires, description=description or (fn.__doc__ or "").split("\n")[0])
            return fn
        return decorator

    def get(self, name: str) -> ToolNode:
        if name not in self._nodes:
            raise MissingTool(name)
        return self._nodes[name]

    def has(self, name: str) -> bool:
        return name in self._nodes

    def names(self) -> list[str]:
        return list(self._nodes.keys())

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, name: str) -> bool:
        return name in self._nodes

    def dependencies(self, name: str, transitive: bool = False) -> list[str]:
        """Return direct (or transitive) dependencies of a tool."""
        node = self.get(name)
        if not transitive:
            return list(node.requires)
        # BFS
        visited: list[str] = []
        seen: set[str] = set()
        queue = list(node.requires)
        while queue:
            dep = queue.pop(0)
            if dep in seen:
                continue
            seen.add(dep)
            visited.append(dep)
            dep_node = self._nodes.get(dep)
            if dep_node:
                queue.extend(dep_node.requires)
        return visited

    def execution_order(self, *targets: str) -> list[str]:
        """
        Return a topologically sorted execution order for the given targets
        (and all their transitive dependencies). Raises CycleError if a cycle
        is detected, MissingTool if a required tool is not registered.
        """
        # collect all nodes reachable from targets
        all_nodes: set[str] = set()
        stack = list(targets)
        while stack:
            n = stack.pop()
            if n in all_nodes:
                continue
            if n not in self._nodes:
                raise MissingTool(n)
            all_nodes.add(n)
            stack.extend(self._nodes[n].requires)

        # Kahn's algorithm for topological sort
        in_degree: dict[str, int] = {n: 0 for n in all_nodes}
        adj: dict[str, list[str]] = {n: [] for n in all_nodes}
        for n in all_nodes:
            for dep in self._nodes[n].requires:
                if dep in all_nodes:
                    adj[dep].append(n)
                    in_degree[n] += 1

        queue = [n for n in all_nodes if in_degree[n] == 0]
        result: list[str] = []
        while queue:
            queue.sort()  # deterministic
            n = queue.pop(0)
            result.append(n)
            for neighbor in adj[n]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(all_nodes):
            raise CycleError("Dependency cycle detected in tool graph")

        return result

    def validate(self) -> list[str]:
        """Return list of validation error strings (empty = valid)."""
        errors: list[str] = []
        # check all requires reference existing tools
        for name, node in self._nodes.items():
            for req in node.requires:
                if req not in self._nodes:
                    errors.append(f"{name}: requires unknown tool '{req}'")
        # check for cycles (only if no missing deps — execution_order raises MissingTool otherwise)
        if not errors:
            try:
                self.execution_order(*self._nodes.keys())
            except CycleError as e:
                errors.append(str(e))
        return errors

    def dependents(self, name: str) -> list[str]:
        """Return tools that directly depend on the given tool."""
        return [n for n, node in self._nodes.items() if name in node.requires]


__all__ = ["ToolGraph", "ToolNode", "CycleError", "MissingTool"]
