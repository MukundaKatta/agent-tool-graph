"""agent-tool-graph - declare tool prerequisites for agent loops.

Agents call tools in a loop. A common failure is the model skipping a
required setup step (calling `query_db` before `login`, or `send_email`
before `verify_recipient`). This library lets you declare those
prerequisites once, then validate every next tool call against the
history.

    from agent_tool_graph import ToolGraph, MissingPrerequisiteError

    g = ToolGraph()
    g.require("query_db", needs="login")
    g.require("send_email", needs={"compose_email", "verify_recipient"})
    g.forbid_after("login", followed_by={"login"})

    history = ["login", "compose_email"]
    g.check("query_db", history)       # ok
    g.check_or_raise("send_email", history)
    # raises MissingPrerequisiteError: missing {"verify_recipient"}

Sibling to `agentvet` (validate tool arguments), `agentguard` (network
egress allowlist), and `tool-loop-guard` (detect repeated tool calls).
"""

from agent_tool_graph.graph import (
    CheckResult,
    ForbiddenSequenceError,
    MissingPrerequisiteError,
    ToolGraph,
    ValidationResult,
)

__version__ = "0.1.0"

__all__ = [
    "CheckResult",
    "ForbiddenSequenceError",
    "MissingPrerequisiteError",
    "ToolGraph",
    "ValidationResult",
    "__version__",
]
