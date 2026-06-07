"""Test package for agent-tool-graph.

Ensures the ``src/`` layout is importable when the test suite is run from a
checkout without an editable install (e.g. ``python3 -m unittest discover -s
tests``). When the package is installed normally this is a harmless no-op
because the already-installed package takes precedence.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)
