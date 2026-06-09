"""
plaid_mcp/server.py

FastMCP server for PlaidMCP.
Exposes finance query tools to Claude Desktop via stdio transport.
"""

import os

os.environ["FASTMCP_LOG_LEVEL"] = "ERROR"
os.environ["FASTMCP_QUIET"] = "1"
os.environ["FASTMCP_NO_BANNER"] = "1"

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from fastmcp import FastMCP
from plaid_mcp.tools.finance_tools import register_finance_tools
from plaid_mcp.tools.statement_tools import register_statement_tools

mcp = FastMCP("plaid-mcp")
register_finance_tools(mcp)
register_statement_tools(mcp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
