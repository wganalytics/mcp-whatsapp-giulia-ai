"""Entrypoint: sobe o servidor MCP evoapi (WhatsApp via Evolution API)."""
from evoapi_mcp import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
