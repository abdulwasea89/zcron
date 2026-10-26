"""Tool catalogue for the assistant agent.

Sensitive read tools enforce capabilities; write tools also pause for
confirmation (ADR 018). New tools are added to the
lists in ``read``/``write`` and flow through here.
"""

from __future__ import annotations

from app.agent.tools.read import READ_TOOLS
from app.agent.tools.write import WRITE_TOOLS

ALL_TOOLS = [*READ_TOOLS, *WRITE_TOOLS]

__all__ = ["ALL_TOOLS", "READ_TOOLS", "WRITE_TOOLS"]
