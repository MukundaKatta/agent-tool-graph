"""Tests for the :class:`agent_tool_graph.SequenceGuard` run-time guard.

Uses only the standard-library ``unittest`` framework.
"""

import os
import sys
import unittest

# Make the ``src/`` layout importable when the suite is run from a checkout
# without an editable install (e.g. ``python3 -m unittest discover -s tests``).
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_tool_graph import (
    ForbiddenSequenceError,
    MissingPrerequisiteError,
    SequenceGuard,
)


class NeedsTests(unittest.TestCase):
    def test_no_rule_is_allowed(self):
        guard = SequenceGuard()
        result = guard.check("anything", [])
        self.assertTrue(result.ok)
        self.assertEqual(result.tool, "anything")

    def test_needs_single_string(self):
        guard = SequenceGuard()
        guard.require("checkout", needs="add_to_cart")
        self.assertTrue(guard.is_allowed("checkout", ["add_to_cart"]))
        self.assertFalse(guard.is_allowed("checkout", []))

    def test_needs_iterable_all_required(self):
        guard = SequenceGuard()
        guard.require("ship", needs=["pack", "label"])
        self.assertTrue(guard.is_allowed("ship", ["pack", "label"]))
        self.assertFalse(guard.is_allowed("ship", ["pack"]))

    def test_missing_prerequisite_error_details(self):
        guard = SequenceGuard()
        guard.require("ship", needs=["pack", "label"])
        with self.assertRaises(MissingPrerequisiteError) as ctx:
            guard.check("ship", ["pack"])
        err = ctx.exception
        self.assertEqual(err.tool, "ship")
        self.assertEqual(err.missing, {"label"})

    def test_needs_any_satisfied_by_one(self):
        guard = SequenceGuard()
        guard.require("notify", needs_any=["email", "sms"])
        self.assertTrue(guard.is_allowed("notify", ["sms"]))
        self.assertTrue(guard.is_allowed("notify", ["email"]))
        self.assertFalse(guard.is_allowed("notify", []))

    def test_needs_any_raises_when_none_present(self):
        guard = SequenceGuard()
        guard.require("notify", needs_any=["email", "sms"])
        with self.assertRaises(MissingPrerequisiteError):
            guard.check("notify", ["push"])

    def test_repeated_require_merges(self):
        guard = SequenceGuard()
        guard.require("x", needs="a")
        guard.require("x", needs="b")
        reqs = guard.requirements_for("x")
        self.assertEqual(reqs["needs"], {"a", "b"})

    def test_require_rejects_empty_tool_name(self):
        guard = SequenceGuard()
        with self.assertRaises(ValueError):
            guard.require("", needs="a")


class ForbidAfterTests(unittest.TestCase):
    def test_forbidden_follow_up_blocked(self):
        guard = SequenceGuard()
        guard.forbid_after("refund", followed_by="checkout")
        self.assertTrue(guard.is_allowed("checkout", []))
        self.assertFalse(guard.is_allowed("checkout", ["refund"]))

    def test_forbidden_error_details(self):
        guard = SequenceGuard()
        guard.forbid_after("refund", followed_by="checkout")
        with self.assertRaises(ForbiddenSequenceError) as ctx:
            guard.check("checkout", ["refund"])
        err = ctx.exception
        self.assertEqual(err.tool, "checkout")
        self.assertEqual(err.after, "refund")

    def test_forbid_after_requires_a_target(self):
        guard = SequenceGuard()
        with self.assertRaises(ValueError):
            guard.forbid_after("refund", followed_by=[])

    def test_forbidden_takes_precedence_over_missing(self):
        # A tool that is both missing a prerequisite *and* forbidden should
        # surface the forbidden error first (more actionable).
        guard = SequenceGuard()
        guard.require("checkout", needs="add_to_cart")
        guard.forbid_after("refund", followed_by="checkout")
        with self.assertRaises(ForbiddenSequenceError):
            guard.check("checkout", ["refund"])


class ValidateSequenceTests(unittest.TestCase):
    def test_valid_sequence(self):
        guard = SequenceGuard()
        guard.require("checkout", needs="add_to_cart")
        result = guard.validate_sequence(["add_to_cart", "checkout"])
        self.assertTrue(result.ok)

    def test_invalid_sequence_reports_first_failure(self):
        guard = SequenceGuard()
        guard.require("checkout", needs="add_to_cart")
        result = guard.validate_sequence(["checkout", "add_to_cart"])
        self.assertFalse(result.ok)
        self.assertEqual(result.failed_index, 0)
        self.assertEqual(result.failed_tool, "checkout")

    def test_sequence_respects_forbid_after(self):
        guard = SequenceGuard()
        guard.forbid_after("refund", followed_by="checkout")
        result = guard.validate_sequence(["refund", "checkout"])
        self.assertFalse(result.ok)
        self.assertEqual(result.failed_index, 1)


class IntrospectionAndPersistenceTests(unittest.TestCase):
    def test_requirements_for_unknown_tool_is_empty(self):
        guard = SequenceGuard()
        reqs = guard.requirements_for("ghost")
        self.assertEqual(reqs["needs"], set())
        self.assertEqual(reqs["needs_any"], set())
        self.assertEqual(reqs["forbid_after"], set())

    def test_tools_lists_declared_rules(self):
        guard = SequenceGuard()
        guard.require("a", needs="b")
        guard.forbid_after("c", followed_by="d")
        self.assertEqual(guard.tools(), {"a", "c"})

    def test_to_dict_is_sorted_and_stable(self):
        guard = SequenceGuard()
        guard.require("x", needs=["c", "a", "b"])
        data = guard.to_dict()
        self.assertEqual(data["x"]["needs"], ["a", "b", "c"])

    def test_round_trip(self):
        guard = SequenceGuard()
        guard.require("checkout", needs="add_to_cart", needs_any=["email", "sms"])
        guard.forbid_after("refund", followed_by="checkout")
        restored = SequenceGuard.from_dict(guard.to_dict())
        self.assertEqual(restored.to_dict(), guard.to_dict())

    def test_round_trip_preserves_forbid_only_rule(self):
        guard = SequenceGuard()
        guard.forbid_after("refund", followed_by="checkout")
        restored = SequenceGuard.from_dict(guard.to_dict())
        self.assertFalse(restored.is_allowed("checkout", ["refund"]))

    def test_from_dict_rejects_non_dict(self):
        with self.assertRaises(TypeError):
            SequenceGuard.from_dict(["not", "a", "dict"])


if __name__ == "__main__":
    unittest.main()
