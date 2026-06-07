"""Tests for the :class:`agent_tool_graph.ToolGraph` dependency DAG.

Uses only the standard-library ``unittest`` framework so the suite runs
with::

    python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

# Make the ``src/`` layout importable when the suite is run from a checkout
# without an editable install (e.g. ``python3 -m unittest discover -s tests``).
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_tool_graph import CycleError, MissingTool, ToolGraph, ToolNode


class AddAndIntrospectionTests(unittest.TestCase):
    def test_add_tool(self):
        g = ToolGraph()
        g.add("fetch")
        self.assertIn("fetch", g)

    def test_add_with_requires(self):
        g = ToolGraph()
        g.add("fetch")
        g.add("parse", requires=["fetch"])
        self.assertEqual(g.get("parse").requires, ["fetch"])

    def test_add_returns_self_for_chaining(self):
        g = ToolGraph()
        result = g.add("a").add("b")
        self.assertIs(result, g)

    def test_get_returns_tool_node(self):
        g = ToolGraph()
        g.add("a", description="alpha", flavor="x")
        node = g.get("a")
        self.assertIsInstance(node, ToolNode)
        self.assertEqual(node.description, "alpha")
        self.assertEqual(node.metadata, {"flavor": "x"})

    def test_get_missing_raises(self):
        g = ToolGraph()
        with self.assertRaises(MissingTool):
            g.get("nope")

    def test_has(self):
        g = ToolGraph()
        g.add("x")
        self.assertTrue(g.has("x"))
        self.assertFalse(g.has("nope"))

    def test_names(self):
        g = ToolGraph()
        g.add("x").add("y")
        self.assertIn("x", g.names())
        self.assertIn("y", g.names())

    def test_len_and_contains(self):
        g = ToolGraph()
        g.add("a").add("b")
        self.assertEqual(len(g), 2)
        self.assertIn("a", g)
        self.assertNotIn("z", g)


class ExecutionOrderTests(unittest.TestCase):
    def test_single(self):
        g = ToolGraph()
        g.add("fetch")
        self.assertEqual(g.execution_order("fetch"), ["fetch"])

    def test_chain_is_ordered(self):
        g = ToolGraph()
        g.add("fetch")
        g.add("parse", requires=["fetch"])
        g.add("extract", requires=["parse"])
        order = g.execution_order("extract")
        self.assertLess(order.index("fetch"), order.index("parse"))
        self.assertLess(order.index("parse"), order.index("extract"))

    def test_diamond(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        g.add("c", requires=["a"])
        g.add("d", requires=["b", "c"])
        order = g.execution_order("d")
        self.assertEqual(order[0], "a")
        self.assertEqual(order[-1], "d")
        self.assertIn("b", order)
        self.assertIn("c", order)

    def test_is_deterministic(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        g.add("c", requires=["a"])
        g.add("d", requires=["b", "c"])
        self.assertEqual(g.execution_order("d"), g.execution_order("d"))

    def test_only_reachable_nodes_included(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        g.add("unrelated")
        order = g.execution_order("b")
        self.assertNotIn("unrelated", order)

    def test_multiple_targets(self):
        g = ToolGraph()
        g.add("a")
        g.add("b")
        g.add("c", requires=["a"])
        order = g.execution_order("b", "c")
        self.assertIn("a", order)
        self.assertIn("b", order)
        self.assertIn("c", order)

    def test_missing_tool_raises(self):
        g = ToolGraph()
        g.add("parse", requires=["missing_tool"])
        with self.assertRaises(MissingTool):
            g.execution_order("parse")

    def test_cycle_detection(self):
        g = ToolGraph()
        g.add("a", requires=["b"])
        g.add("b", requires=["a"])
        with self.assertRaises(CycleError):
            g.execution_order("a")


class DependencyQueryTests(unittest.TestCase):
    def test_direct_dependencies(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        self.assertEqual(g.dependencies("b"), ["a"])

    def test_transitive_dependencies(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        g.add("c", requires=["b"])
        deps = g.dependencies("c", transitive=True)
        self.assertIn("a", deps)
        self.assertIn("b", deps)

    def test_transitive_handles_diamond_without_duplicates(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        g.add("c", requires=["a"])
        g.add("d", requires=["b", "c"])
        deps = g.dependencies("d", transitive=True)
        self.assertEqual(deps.count("a"), 1)

    def test_dependents(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        g.add("c", requires=["a"])
        deps = g.dependents("a")
        self.assertIn("b", deps)
        self.assertIn("c", deps)


class ValidateTests(unittest.TestCase):
    def test_valid_graph(self):
        g = ToolGraph()
        g.add("a")
        g.add("b", requires=["a"])
        self.assertEqual(g.validate(), [])

    def test_missing_dependency_reported(self):
        g = ToolGraph()
        g.add("b", requires=["a"])
        errors = g.validate()
        self.assertTrue(any("unknown tool" in e for e in errors))

    def test_cycle_reported(self):
        g = ToolGraph()
        g.add("a", requires=["b"])
        g.add("b", requires=["a"])
        errors = g.validate()
        self.assertTrue(any("cycle" in e.lower() for e in errors))


class RegisterDecoratorTests(unittest.TestCase):
    def test_register_uses_function_name(self):
        g = ToolGraph()

        @g.register()
        def my_tool():
            """My tool."""

        self.assertIn("my_tool", g)

    def test_register_captures_docstring_and_requires(self):
        g = ToolGraph()
        g.add("prereq")

        @g.register(requires=["prereq"])
        def downstream():
            """First line.\nSecond line."""

        node = g.get("downstream")
        self.assertEqual(node.requires, ["prereq"])
        self.assertEqual(node.description, "First line.")

    def test_register_returns_original_function(self):
        g = ToolGraph()

        @g.register()
        def fn():
            return 42

        self.assertEqual(fn(), 42)


if __name__ == "__main__":
    unittest.main()
