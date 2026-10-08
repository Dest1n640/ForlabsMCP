"""CLI entry point: builds the MCPServer with a lazily-created
ForlabsClient and runs it over stdio.

Building the server never touches the network or even loads
configuration - both are deferred to the client factory, which only
runs when a tool is actually invoked. This means starting the process
(even with no credentials configured) never requires a live backend
connection.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .client.client import ForlabsClient
from .config import assignment_submission_enabled_from_env, load_config
from .tools.register import register_tools


def build_server() -> MCPServer:
    server = MCPServer("forlabs")

    client: ForlabsClient | None = None

    def client_factory() -> ForlabsClient:
        nonlocal client
        if client is None:
            client = ForlabsClient(load_config())
        return client

    register_tools(
        server,
        client_factory,
        submission_enabled=assignment_submission_enabled_from_env(),
    )
    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
