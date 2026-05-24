# agent-tool-graph

[![PyPI](https://img.shields.io/pypi/v/agent-tool-graph.svg)](https://pypi.org/project/agent-tool-graph/)
[![Python](https://img.shields.io/pypi/pyversions/agent-tool-graph.svg)](https://pypi.org/project/agent-tool-graph/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Declare tool prerequisites for agent loops.**

Agents call tools in a loop. A common failure is the model skipping a
required setup step (calling `query_db` before `login`, or `send_email`
before `verify_recipient`). This library lets you declare those
prerequisites once, then validate every next tool call against the
history. Zero runtime dependencies.

## Install

```bash
pip install agent-tool-graph
```

## Use

```python
from agent_tool_graph import ToolGraph, MissingPrerequisiteError

g = ToolGraph()
g.require("query_db", needs="login")
g.require("send_email", needs={"compose_email", "verify_recipient"})
g.require("checkout", needs_any={"add_to_cart", "buy_now"})
g.forbid_after("login", followed_by={"login"})  # do not log in twice

history = ["login", "compose_email"]

g.check("verify_recipient", history)  # ok
g.check("query_db", history)          # ok (login is present)

try:
    g.check("send_email", history)
except MissingPrerequisiteError as e:
    print(e.missing)  # {"verify_recipient"}
```

`needs=...` is an ALL gate: every name listed must appear in history.
`needs_any=...` is an ANY gate: at least one of the listed names must
appear. The two can be combined on the same tool.

## Validate a planned sequence

When the agent proposes a multi-step plan, you can validate the entire
order in one shot:

```python
result = g.validate_sequence([
    "login",
    "compose_email",
    "verify_recipient",
    "send_email",
])

if result.ok:
    run_plan()
else:
    print(f"step {result.failed_index}: {result.reason}")
```

The validator stops at the first failing step and returns its index, the
tool name, and the closed-form reason.

## Non-raising check

```python
if g.is_allowed("send_email", history):
    do_it()
else:
    ask_model_to_compose_first()
```

## JSON round-trip

Persist the graph to disk or send it over the wire:

```python
import json

blob = json.dumps(g.to_dict())
# ... later ...
g2 = ToolGraph.from_dict(json.loads(blob))
assert g2.requirements_for("send_email") == g.requirements_for("send_email")
```

## Introspection

```python
g.requirements_for("send_email")
# {
#   "needs": {"compose_email", "verify_recipient"},
#   "needs_any": set(),
#   "forbid_after": set(),
# }
```

## Siblings

Same author, same agent-stack family:

- [`agentvet`](https://pypi.org/project/agentvet/) - validate tool
  arguments before calling the tool.
- [`agentguard`](https://pypi.org/project/agentguard/) - declarative
  network egress allowlist for agent tools.
- [`tool-loop-guard`](https://pypi.org/project/tool-loop-guard/) -
  detect repeated tool calls to break agent loops early.

`agent-tool-graph` fits in front of the tool dispatcher: declare
prerequisites once, call `g.check_or_raise(name, history)` before each
tool call.

## What it does NOT do

- No DAG execution. This is a validator over an existing history list,
  not a scheduler or planner.
- No automatic history tracking. Pass the list of completed tool names
  yourself. (You almost certainly already have it on the message log.)
- No LLM call. Doesn't talk to any provider.
- No cycle prevention beyond the rules you declare. If you want "no
  same-tool twice in a row", use `forbid_after`.

## License

MIT
