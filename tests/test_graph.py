import json

import pytest

from agent_tool_graph import (
    CheckResult,
    ForbiddenSequenceError,
    MissingPrerequisiteError,
    ToolGraph,
    ValidationResult,
)

# ---------- basic empty / passthrough behavior ----------


def test_empty_graph_allows_anything():
    g = ToolGraph()
    assert g.is_allowed("anything", [])
    assert g.is_allowed("foo", ["bar", "baz"])
    result = g.check("anything", [])
    assert isinstance(result, CheckResult)
    assert result.ok is True


def test_tool_with_no_rule_is_always_allowed():
    g = ToolGraph()
    g.require("known", needs="other")
    # unknown tool name has no rule; passes regardless of history
    assert g.is_allowed("unrelated", [])
    assert g.is_allowed("unrelated", ["known"])


# ---------- single needs ----------


def test_require_single_needs_passes_when_met():
    g = ToolGraph()
    g.require("query_db", needs="login")
    g.check_or_raise("query_db", ["login"])
    assert g.is_allowed("query_db", ["login", "other"])


def test_require_single_needs_fails_when_missing():
    g = ToolGraph()
    g.require("query_db", needs="login")
    with pytest.raises(MissingPrerequisiteError) as exc:
        g.check_or_raise("query_db", [])
    assert exc.value.tool == "query_db"
    assert exc.value.missing == {"login"}


# ---------- multi needs (ALL) ----------


def test_require_multi_needs_all_must_be_present():
    g = ToolGraph()
    g.require("send_email", needs={"compose_email", "verify_recipient"})

    # both present -> ok
    g.check_or_raise("send_email", ["compose_email", "verify_recipient"])

    # one missing -> raises and reports just the missing piece
    with pytest.raises(MissingPrerequisiteError) as exc:
        g.check_or_raise("send_email", ["compose_email"])
    assert exc.value.missing == {"verify_recipient"}

    # both missing -> reports both
    with pytest.raises(MissingPrerequisiteError) as exc:
        g.check_or_raise("send_email", [])
    assert exc.value.missing == {"compose_email", "verify_recipient"}


# ---------- needs_any (ONE) ----------


def test_needs_any_passes_when_one_present():
    g = ToolGraph()
    g.require("checkout", needs_any={"add_to_cart", "buy_now"})
    g.check_or_raise("checkout", ["add_to_cart"])
    g.check_or_raise("checkout", ["buy_now"])
    g.check_or_raise("checkout", ["add_to_cart", "buy_now"])


def test_needs_any_fails_when_none_present():
    g = ToolGraph()
    g.require("checkout", needs_any={"add_to_cart", "buy_now"})
    with pytest.raises(MissingPrerequisiteError) as exc:
        g.check_or_raise("checkout", ["browse"])
    # the whole needs_any set is the "missing" payload here
    assert exc.value.missing == {"add_to_cart", "buy_now"}


def test_needs_and_needs_any_combined():
    g = ToolGraph()
    g.require("publish", needs="login", needs_any={"draft", "import"})
    g.check_or_raise("publish", ["login", "draft"])
    # missing the ALL gate
    with pytest.raises(MissingPrerequisiteError):
        g.check_or_raise("publish", ["draft"])
    # missing the ANY gate
    with pytest.raises(MissingPrerequisiteError):
        g.check_or_raise("publish", ["login"])


# ---------- forbid_after ----------


def test_forbid_after_blocks_followup():
    g = ToolGraph()
    g.forbid_after("login", followed_by={"login"})
    g.check_or_raise("login", [])  # first time fine
    with pytest.raises(ForbiddenSequenceError) as exc:
        g.check_or_raise("login", ["login"])
    assert exc.value.tool == "login"
    assert exc.value.after == "login"


def test_forbid_after_multiple_targets():
    g = ToolGraph()
    g.forbid_after("refund", followed_by={"charge", "ship"})
    g.check_or_raise("charge", [])
    g.check_or_raise("ship", [])
    with pytest.raises(ForbiddenSequenceError):
        g.check_or_raise("charge", ["refund"])
    with pytest.raises(ForbiddenSequenceError):
        g.check_or_raise("ship", ["refund", "other"])


def test_forbid_after_can_chain_with_other_rules():
    g = ToolGraph()
    g.require("send_email", needs={"compose_email"})
    g.forbid_after("send_email", followed_by={"send_email"})
    g.check_or_raise("send_email", ["compose_email"])
    with pytest.raises(ForbiddenSequenceError):
        g.check_or_raise("send_email", ["compose_email", "send_email"])


# ---------- check vs check_or_raise vs is_allowed ----------


def test_check_or_raise_raises_with_right_type():
    g = ToolGraph()
    g.require("a", needs="b")
    g.forbid_after("x", followed_by={"y"})

    with pytest.raises(MissingPrerequisiteError):
        g.check_or_raise("a", [])
    with pytest.raises(ForbiddenSequenceError):
        g.check_or_raise("y", ["x"])


def test_check_returns_result_on_success():
    g = ToolGraph()
    g.require("a", needs="b")
    result = g.check("a", ["b"])
    assert result.ok is True
    assert result.tool == "a"
    assert result.reason


def test_is_allowed_does_not_raise():
    g = ToolGraph()
    g.require("a", needs="b")
    g.forbid_after("x", followed_by={"y"})
    assert g.is_allowed("a", ["b"]) is True
    assert g.is_allowed("a", []) is False
    assert g.is_allowed("y", ["x"]) is False
    assert g.is_allowed("y", []) is True


# ---------- validate_sequence ----------


def test_validate_sequence_passes_full_plan():
    g = ToolGraph()
    g.require("query_db", needs="login")
    g.require("respond", needs="query_db")
    result = g.validate_sequence(["login", "query_db", "respond"])
    assert isinstance(result, ValidationResult)
    assert result.ok is True
    assert result.failed_index is None


def test_validate_sequence_reports_first_failure():
    g = ToolGraph()
    g.require("query_db", needs="login")
    g.require("respond", needs="query_db")
    # missing login -> fails at step 0
    result = g.validate_sequence(["query_db", "respond"])
    assert result.ok is False
    assert result.failed_index == 0
    assert result.failed_tool == "query_db"
    assert "login" in result.reason


def test_validate_sequence_stops_at_first_failure_not_last():
    g = ToolGraph()
    g.require("a", needs="setup")
    g.require("b", needs="setup")
    g.require("c", needs="setup")
    # all three need setup; the validator should stop at step 0
    result = g.validate_sequence(["a", "b", "c"])
    assert result.failed_index == 0
    assert result.failed_tool == "a"


def test_validate_sequence_catches_forbidden_sequence():
    g = ToolGraph()
    g.forbid_after("login", followed_by={"login"})
    result = g.validate_sequence(["login", "login"])
    assert result.ok is False
    assert result.failed_index == 1
    assert result.failed_tool == "login"


# ---------- chained requirements (A -> B -> C) ----------


def test_chained_requirements_a_b_c():
    g = ToolGraph()
    g.require("B", needs="A")
    g.require("C", needs="B")
    # A is fine
    g.check_or_raise("A", [])
    # B needs A
    with pytest.raises(MissingPrerequisiteError):
        g.check_or_raise("B", [])
    g.check_or_raise("B", ["A"])
    # C needs B (not A!) per the declared rule
    with pytest.raises(MissingPrerequisiteError):
        g.check_or_raise("C", ["A"])
    g.check_or_raise("C", ["A", "B"])
    # validate_sequence picks this up in one shot
    assert g.validate_sequence(["A", "B", "C"]).ok is True


# ---------- requirements_for introspection ----------


def test_requirements_for_returns_declared_rule():
    g = ToolGraph()
    g.require("send_email", needs={"compose_email", "verify_recipient"})
    g.require("send_email", needs_any={"address_book", "manual_entry"})
    g.forbid_after("send_email", followed_by={"send_email"})
    req = g.requirements_for("send_email")
    assert req["needs"] == {"compose_email", "verify_recipient"}
    assert req["needs_any"] == {"address_book", "manual_entry"}
    assert req["forbid_after"] == {"send_email"}


def test_requirements_for_unknown_tool_returns_empty_sets():
    g = ToolGraph()
    req = g.requirements_for("does_not_exist")
    assert req == {"needs": set(), "needs_any": set(), "forbid_after": set()}


def test_repeated_require_merges_rather_than_replacing():
    g = ToolGraph()
    g.require("t", needs="a")
    g.require("t", needs="b")  # adds, not replaces
    assert g.requirements_for("t")["needs"] == {"a", "b"}


# ---------- to_dict / from_dict ----------


def test_to_dict_from_dict_round_trip():
    g = ToolGraph()
    g.require("query_db", needs="login")
    g.require("send_email", needs={"compose_email", "verify_recipient"})
    g.require("checkout", needs_any={"add_to_cart"})
    g.forbid_after("login", followed_by={"login"})

    blob = json.dumps(g.to_dict())
    g2 = ToolGraph.from_dict(json.loads(blob))

    for tool in ["query_db", "send_email", "checkout", "login"]:
        assert g2.requirements_for(tool) == g.requirements_for(tool)

    # behavior is preserved end-to-end
    history = ["login", "compose_email", "verify_recipient"]
    assert g2.is_allowed("send_email", history)
    with pytest.raises(ForbiddenSequenceError):
        g2.check_or_raise("login", history)


def test_to_dict_output_is_stable_sorted_lists():
    g = ToolGraph()
    g.require("t", needs={"c", "a", "b"})
    d = g.to_dict()
    assert d["t"]["needs"] == ["a", "b", "c"]  # sorted


def test_from_dict_rejects_non_dict():
    with pytest.raises(TypeError):
        ToolGraph.from_dict("not a dict")  # type: ignore[arg-type]


# ---------- input validation ----------


def test_require_rejects_empty_tool_name():
    g = ToolGraph()
    with pytest.raises(ValueError):
        g.require("", needs="x")


def test_forbid_after_requires_followed_by():
    g = ToolGraph()
    with pytest.raises(ValueError):
        g.forbid_after("t", followed_by=set())


def test_require_accepts_iterable_or_single_string():
    g = ToolGraph()
    g.require("a", needs="x")
    g.require("b", needs=["x", "y"])
    g.require("c", needs={"x", "y", "z"})
    assert g.requirements_for("a")["needs"] == {"x"}
    assert g.requirements_for("b")["needs"] == {"x", "y"}
    assert g.requirements_for("c")["needs"] == {"x", "y", "z"}


def test_tools_lists_declared_names():
    g = ToolGraph()
    g.require("a", needs="x")
    g.forbid_after("b", followed_by={"y"})
    assert g.tools() == {"a", "b"}
