"""Tests for agent-tool-graph."""

import pytest
from agent_tool_graph import ToolGraph, ToolNode, CycleError, MissingTool


def test_add_tool():
    g = ToolGraph()
    g.add("fetch")
    assert "fetch" in g


def test_add_with_requires():
    g = ToolGraph()
    g.add("fetch")
    g.add("parse", requires=["fetch"])
    assert g.get("parse").requires == ["fetch"]


def test_execution_order_single():
    g = ToolGraph()
    g.add("fetch")
    assert g.execution_order("fetch") == ["fetch"]


def test_execution_order_chain():
    g = ToolGraph()
    g.add("fetch")
    g.add("parse", requires=["fetch"])
    g.add("extract", requires=["parse"])
    order = g.execution_order("extract")
    assert order.index("fetch") < order.index("parse") < order.index("extract")


def test_execution_order_diamond():
    g = ToolGraph()
    g.add("a")
    g.add("b", requires=["a"])
    g.add("c", requires=["a"])
    g.add("d", requires=["b", "c"])
    order = g.execution_order("d")
    assert order[0] == "a"
    assert order[-1] == "d"
    assert "b" in order and "c" in order


def test_execution_order_missing_tool():
    g = ToolGraph()
    g.add("fetch")
    g.add("parse", requires=["missing_tool"])
    with pytest.raises(MissingTool):
        g.execution_order("parse")


def test_cycle_detection():
    g = ToolGraph()
    g.add("a", requires=["b"])
    g.add("b", requires=["a"])
    with pytest.raises(CycleError):
        g.execution_order("a")


def test_dependencies_direct():
    g = ToolGraph()
    g.add("a")
    g.add("b", requires=["a"])
    assert g.dependencies("b") == ["a"]


def test_dependencies_transitive():
    g = ToolGraph()
    g.add("a")
    g.add("b", requires=["a"])
    g.add("c", requires=["b"])
    deps = g.dependencies("c", transitive=True)
    assert "a" in deps and "b" in deps


def test_dependents():
    g = ToolGraph()
    g.add("a")
    g.add("b", requires=["a"])
    g.add("c", requires=["a"])
    deps = g.dependents("a")
    assert "b" in deps and "c" in deps


def test_get_missing():
    g = ToolGraph()
    with pytest.raises(MissingTool):
        g.get("nope")


def test_has_false():
    g = ToolGraph()
    assert g.has("nope") is False


def test_names():
    g = ToolGraph()
    g.add("x").add("y")
    assert "x" in g.names()
    assert "y" in g.names()


def test_len():
    g = ToolGraph()
    g.add("a").add("b")
    assert len(g) == 2


def test_validate_ok():
    g = ToolGraph()
    g.add("a")
    g.add("b", requires=["a"])
    assert g.validate() == []


def test_validate_missing_dep():
    g = ToolGraph()
    g.add("b", requires=["a"])
    errors = g.validate()
    assert any("unknown tool" in e for e in errors)


def test_validate_cycle():
    g = ToolGraph()
    g.add("a", requires=["b"])
    g.add("b", requires=["a"])
    errors = g.validate()
    assert any("cycle" in e.lower() for e in errors)


def test_register_decorator():
    g = ToolGraph()

    @g.register()
    def my_tool():
        """My tool."""

    assert "my_tool" in g


def test_chaining():
    g = ToolGraph()
    result = g.add("a").add("b")
    assert result is g


def test_multiple_targets():
    g = ToolGraph()
    g.add("a")
    g.add("b")
    g.add("c", requires=["a"])
    order = g.execution_order("b", "c")
    assert "b" in order and "c" in order and "a" in order


def test_get_returns_toolnode():
    g = ToolGraph()
    g.add("fetch", description="fetch a page", region="eu")
    node = g.get("fetch")
    assert isinstance(node, ToolNode)
    assert node.name == "fetch"
    assert node.description == "fetch a page"
    assert node.metadata == {"region": "eu"}


def test_register_decorator_records_requires():
    g = ToolGraph()
    g.add("setup")

    @g.register(requires=["setup"])
    def my_tool():
        """My tool docstring."""

    node = g.get("my_tool")
    assert node.requires == ["setup"]
    assert node.description == "My tool docstring."


def test_execution_order_unknown_target():
    g = ToolGraph()
    with pytest.raises(MissingTool):
        g.execution_order("nope")


def test_validate_unknown_dep_lists_offender():
    g = ToolGraph()
    g.add("b", requires=["a"])
    errors = g.validate()
    assert errors == ["b: requires unknown tool 'a'"]
