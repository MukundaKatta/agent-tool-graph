# agent-tool-graph

Declarative tool prerequisites — define which tools must run before others and get a guaranteed execution order.

```python
from agent_tool_graph import ToolGraph

g = ToolGraph()
g.add("fetch_page")
g.add("parse_html", requires=["fetch_page"])
g.add("extract_data", requires=["parse_html"])

order = g.execution_order("extract_data")
# ["fetch_page", "parse_html", "extract_data"]

errors = g.validate()  # detect missing deps + cycles before running
```

Cycle detection via Kahn's algorithm. Raises `CycleError` or `MissingTool`.
