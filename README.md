# agent-tool-graph

Declarative tool prerequisites for agent workflows — decide what order tools
should run in, and enforce those rules while the agent is running.

The library ships two small, dependency-free primitives:

| Primitive | Question it answers | When you use it |
|-----------|---------------------|-----------------|
| [`ToolGraph`](#toolgraph--static-dependency-planning) | *"In what order should these tools run?"* | Ahead of time, to build a plan |
| [`SequenceGuard`](#sequenceguard--run-time-guarding) | *"Given what already ran, may this tool run now?"* | At run time, on every tool call |

Plan with `ToolGraph.execution_order`, then guard the live call stream with
`SequenceGuard.check`.

## Install

The package has no runtime dependencies and targets Python 3.10+.

```bash
pip install agent-tool-graph
```

Or from a checkout:

```bash
pip install -e .
```

## `ToolGraph` — static dependency planning

Register tools with their prerequisites, then ask for a topologically-sorted
execution order, list dependencies, or validate the whole graph up front.

```python
from agent_tool_graph import ToolGraph

g = ToolGraph()
g.add("fetch_page")
g.add("parse_html", requires=["fetch_page"])
g.add("extract_data", requires=["parse_html"])

g.execution_order("extract_data")
# ['fetch_page', 'parse_html', 'extract_data']

g.dependencies("extract_data", transitive=True)
# ['parse_html', 'fetch_page']

g.validate()  # [] when the graph is sound
```

Cycles and dangling references are caught before anything runs:

```python
from agent_tool_graph import ToolGraph, CycleError, MissingTool

g = ToolGraph()
g.add("a", requires=["b"])
g.add("b", requires=["a"])

g.validate()
# ['Dependency cycle detected in tool graph']

g.execution_order("a")   # raises CycleError
g.add("c", requires=["ghost"])
g.execution_order("c")   # raises MissingTool
```

`execution_order` is deterministic: among tools that are ready at the same
time, names are emitted in sorted order, so repeated runs produce identical
plans.

You can also register tools with a decorator, which captures the function name
and the first line of its docstring:

```python
g = ToolGraph()

@g.register(requires=["fetch_page"])
def parse_html():
    """Parse a fetched page into a DOM."""

"parse_html" in g  # True
```

## `SequenceGuard` — run-time guarding

A `SequenceGuard` checks a single tool call against the *history* of tools that
have already run. It supports hard prerequisites (`needs`), "at least one of"
prerequisites (`needs_any`), and forbidden follow-ups (`forbid_after`).

```python
from agent_tool_graph import SequenceGuard

guard = SequenceGuard()
guard.require("checkout", needs="add_to_cart")
guard.require("notify", needs_any=["email", "sms"])
guard.forbid_after("refund", followed_by="checkout")

guard.is_allowed("checkout", ["add_to_cart"])  # True
guard.is_allowed("checkout", [])               # False — missing prerequisite
guard.is_allowed("checkout", ["refund"])       # False — forbidden after refund
```

`check` raises a descriptive exception so you can surface *why* a call was
blocked:

```python
from agent_tool_graph import MissingPrerequisiteError, ForbiddenSequenceError

try:
    guard.check("checkout", [])
except MissingPrerequisiteError as e:
    print(e.tool, e.missing)   # 'checkout' {'add_to_cart'}
```

Validate a whole planned sequence at once; it stops at the first violation:

```python
result = guard.validate_sequence(["checkout", "add_to_cart"])
result.ok            # False
result.failed_index  # 0
result.failed_tool   # 'checkout'
```

Rules round-trip to a JSON-friendly dict for storage or transport:

```python
data = guard.to_dict()
restored = SequenceGuard.from_dict(data)
```

## API reference

### `ToolGraph`

| Method | Description |
|--------|-------------|
| `add(name, requires=None, description="", **metadata)` | Register a tool. Returns `self` for chaining. |
| `register(requires=None, description="")` | Decorator form of `add`. |
| `get(name)` | Return the `ToolNode`; raises `MissingTool`. |
| `has(name)` / `name in g` | Membership test. |
| `names()` | All registered tool names. |
| `dependencies(name, transitive=False)` | Direct (or transitive) prerequisites. |
| `dependents(name)` | Tools that directly require `name`. |
| `execution_order(*targets)` | Topologically-sorted plan; raises `CycleError` / `MissingTool`. |
| `validate()` | List of error strings (empty when sound). |
| `len(g)` | Number of registered tools. |

### `SequenceGuard`

| Method | Description |
|--------|-------------|
| `require(tool, *, needs=None, needs_any=None)` | Declare prerequisites (merges on repeat). |
| `forbid_after(tool, *, followed_by)` | Forbid follow-up tools once `tool` has run. |
| `check(tool, history)` | Return a `CheckResult`; raises on failure. |
| `check_or_raise(tool, history)` | Raise-only variant. |
| `is_allowed(tool, history)` | Non-raising boolean. |
| `validate_sequence(seq)` | Walk a planned sequence; returns a `ValidationResult`. |
| `requirements_for(tool)` | Inspect declared rules for one tool. |
| `tools()` | All tool names that have a rule. |
| `to_dict()` / `from_dict(data)` | JSON-friendly round-trip. |

### Exceptions

- `CycleError` — a dependency cycle was detected (`ToolGraph`).
- `MissingTool` — a referenced tool is not registered (`ToolGraph`).
- `MissingPrerequisiteError` — `needs` / `needs_any` not satisfied (`SequenceGuard`).
- `ForbiddenSequenceError` — a `forbid_after` rule blocked the call (`SequenceGuard`).

## Development

Run the test suite with the standard library only — no third-party tooling
required:

```bash
python -m unittest discover -s tests
```

## License

MIT — see [LICENSE](LICENSE).
