"""Core ToolGraph implementation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


def _coerce_names(value: str | Iterable[str] | None) -> set[str]:
    """Accept a single tool name, an iterable, or None. Return a fresh set."""
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    names = set(value)
    for name in names:
        if not isinstance(name, str):
            raise TypeError(f"tool names must be str, got {type(name).__name__}")
    return names


class MissingPrerequisiteError(Exception):
    """Raised when a tool is checked against a history that does not
    satisfy its `needs` / `needs_any` requirements.

    Attributes:
        tool: the tool that was being checked
        missing: the set of tool names that were required but absent
        reason: human-readable explanation
    """

    def __init__(self, tool: str, missing: set[str], reason: str):
        self.tool = tool
        self.missing = set(missing)
        self.reason = reason
        super().__init__(reason)


class ForbiddenSequenceError(Exception):
    """Raised when a tool is checked but a previously-run tool has
    explicitly forbidden it as a follow-up.

    Attributes:
        tool: the tool that was being checked
        after: the earlier tool that forbids this follow-up
        reason: human-readable explanation
    """

    def __init__(self, tool: str, after: str, reason: str):
        self.tool = tool
        self.after = after
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class CheckResult:
    """Return value of `ToolGraph.check`. `ok` is True when the tool may
    run given the history. On failure, exactly one of `missing` or
    `forbidden_after` is populated and `reason` carries a description."""

    ok: bool
    tool: str
    missing: frozenset[str] = frozenset()
    forbidden_after: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class ValidationResult:
    """Return value of `ToolGraph.validate_sequence`. If `ok` is False,
    `failed_index` and `failed_tool` point at the first failing step."""

    ok: bool
    failed_index: int | None = None
    failed_tool: str | None = None
    reason: str = ""


@dataclass
class _Rule:
    """Internal record of a single tool's declared prerequisites."""

    needs: set[str] = field(default_factory=set)
    needs_any: set[str] = field(default_factory=set)
    forbid_after: set[str] = field(default_factory=set)


class ToolGraph:
    """Declarative graph of tool prerequisites.

    Methods:
      * `require(tool, needs=..., needs_any=...)` declare prerequisites.
      * `forbid_after(tool, followed_by=...)` declare a forbidden follow-up.
      * `check(tool, history)` return a `CheckResult` and raise on failure.
      * `check_or_raise(tool, history)` raise-only variant.
      * `is_allowed(tool, history)` non-raising boolean.
      * `validate_sequence(seq)` walk a planned sequence in order.
      * `requirements_for(tool)` introspect declared rules for one tool.
      * `to_dict()` / `from_dict()` JSON-friendly round-trip.
    """

    def __init__(self) -> None:
        self._rules: dict[str, _Rule] = {}

    # ---- declaration ----

    def require(
        self,
        tool: str,
        *,
        needs: str | Iterable[str] | None = None,
        needs_any: str | Iterable[str] | None = None,
    ) -> None:
        """Declare prerequisites for `tool`.

        - `needs`: every listed tool name must appear in history.
        - `needs_any`: at least one listed tool name must appear.

        Repeated calls for the same tool merge into the existing rule
        rather than replacing it.
        """
        if not isinstance(tool, str) or not tool:
            raise ValueError("tool must be a non-empty string")
        rule = self._rules.setdefault(tool, _Rule())
        rule.needs |= _coerce_names(needs)
        rule.needs_any |= _coerce_names(needs_any)

    def forbid_after(
        self,
        tool: str,
        *,
        followed_by: str | Iterable[str],
    ) -> None:
        """After `tool` has appeared in history, none of `followed_by`
        may run next or later. Useful for "do not log in twice" or
        "no checkout after refund".

        Repeated calls merge into the existing forbid-set.
        """
        if not isinstance(tool, str) or not tool:
            raise ValueError("tool must be a non-empty string")
        forbid = _coerce_names(followed_by)
        if not forbid:
            raise ValueError("forbid_after needs at least one followed_by name")
        rule = self._rules.setdefault(tool, _Rule())
        rule.forbid_after |= forbid

    # ---- checking ----

    def check(self, tool: str, history: Sequence[str]) -> CheckResult:
        """Return a `CheckResult` and raise on failure.

        On failure, raises `MissingPrerequisiteError` (needs/needs_any
        not satisfied) or `ForbiddenSequenceError` (some earlier tool's
        forbid_after blocks this one). On success, returns
        `CheckResult(ok=True, ...)`.
        """
        if not isinstance(tool, str) or not tool:
            raise ValueError("tool must be a non-empty string")
        history_set = set(history)

        # Forbidden-after check first: it gives a more useful error than
        # "missing prerequisite X" when the agent is repeating itself.
        for prior, rule in self._rules.items():
            if tool in rule.forbid_after and prior in history_set:
                reason = f"tool {tool!r} is forbidden after {prior!r} has run"
                raise ForbiddenSequenceError(tool, prior, reason)

        rule = self._rules.get(tool)
        if rule is None:
            return CheckResult(ok=True, tool=tool, reason="no rule declared")

        missing = rule.needs - history_set
        if missing:
            reason = (
                f"tool {tool!r} requires {sorted(rule.needs)} in history;"
                f" missing {sorted(missing)}"
            )
            raise MissingPrerequisiteError(tool, missing, reason)

        if rule.needs_any and rule.needs_any.isdisjoint(history_set):
            reason = (
                f"tool {tool!r} requires any of {sorted(rule.needs_any)}"
                f" in history; none found"
            )
            raise MissingPrerequisiteError(tool, set(rule.needs_any), reason)

        return CheckResult(ok=True, tool=tool, reason="ok")

    def check_or_raise(self, tool: str, history: Sequence[str]) -> None:
        """Raise on failure, return None on success."""
        self.check(tool, history)

    def is_allowed(self, tool: str, history: Sequence[str]) -> bool:
        """Non-raising convenience. Returns True iff `check` would pass."""
        try:
            self.check(tool, history)
        except (MissingPrerequisiteError, ForbiddenSequenceError):
            return False
        return True

    def validate_sequence(self, sequence: Sequence[str]) -> ValidationResult:
        """Validate a planned sequence in order. The first call is
        checked against an empty history, the second against
        `[sequence[0]]`, and so on. Stops at the first failure."""
        history: list[str] = []
        for i, tool in enumerate(sequence):
            try:
                self.check(tool, history)
            except (MissingPrerequisiteError, ForbiddenSequenceError) as e:
                return ValidationResult(
                    ok=False,
                    failed_index=i,
                    failed_tool=tool,
                    reason=str(e),
                )
            history.append(tool)
        return ValidationResult(ok=True, reason="all steps pass")

    # ---- introspection ----

    def requirements_for(self, tool: str) -> dict[str, set[str]]:
        """Return the declared rules for `tool` as a dict with three
        keys: `needs`, `needs_any`, `forbid_after`. The `forbid_after`
        set contains tools that, if run after `tool`, would be blocked."""
        rule = self._rules.get(tool, _Rule())
        return {
            "needs": set(rule.needs),
            "needs_any": set(rule.needs_any),
            "forbid_after": set(rule.forbid_after),
        }

    def tools(self) -> set[str]:
        """All tool names that have a declared rule."""
        return set(self._rules.keys())

    # ---- persistence ----

    def to_dict(self) -> dict[str, dict[str, list[str]]]:
        """Serialize to a JSON-friendly dict. Sets become sorted lists
        so the output is stable across runs (handy for diffing)."""
        return {
            name: {
                "needs": sorted(rule.needs),
                "needs_any": sorted(rule.needs_any),
                "forbid_after": sorted(rule.forbid_after),
            }
            for name, rule in self._rules.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, dict[str, list[str]]]) -> ToolGraph:
        """Round-trip companion to `to_dict()`. Tolerates missing keys."""
        if not isinstance(data, dict):
            raise TypeError("from_dict expects a dict")
        g = cls()
        for name, rule_data in data.items():
            if not isinstance(rule_data, dict):
                raise TypeError(f"rule for {name!r} must be a dict")
            needs = rule_data.get("needs", [])
            needs_any = rule_data.get("needs_any", [])
            forbid_after = rule_data.get("forbid_after", [])
            if needs or needs_any:
                g.require(name, needs=needs, needs_any=needs_any)
            else:
                # Still register the tool so `forbid_after` declarations
                # round-trip even when there are no `needs`.
                g._rules.setdefault(name, _Rule())
            if forbid_after:
                g.forbid_after(name, followed_by=forbid_after)
        return g
