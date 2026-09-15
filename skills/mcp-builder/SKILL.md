---
name: mcp-builder
description: Build MCP servers to give agents new tools (Python FastMCP or TS SDK).
---

# mcp-builder

Model Context Protocol server = a tool provider any MCP client (this app) can load.

Python (FastMCP):
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("myserver")
@mcp.tool()
def add(a: int, b: int) -> int:
    "Add two numbers."
    return a + b
if __name__ == "__main__":
    mcp.run()   # stdio transport
```
Register it in Customize → Connectors: transport stdio, command `python myserver.py`.

Tips: one clear job per tool, typed args + docstrings (they become the schema),
return plain text/JSON, fail with a readable message. TS: `@modelcontextprotocol/sdk`.
