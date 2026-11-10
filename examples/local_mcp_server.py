"""Local test MCP server for the live capability-router examples."""

from fastmcp import FastMCP

server = FastMCP("agskillmanager-local-tools")


@server.tool(name="github.pull_request.read")
async def read_pull_request(number: int = 42) -> dict[str, object]:
    """Return a fixed, non-sensitive pull-request example."""
    return {
        "number": number,
        "title": "Document transaction safety checks",
        "state": "open",
    }


if __name__ == "__main__":
    server.run(transport="http", host="127.0.0.1", port=8765, stateless_http=True)
