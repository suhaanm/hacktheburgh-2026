# MCP ecosystem (CONNECTIONS reference note)

Read-only study on 7 Nov 2026; nothing from it was run. Full source list: `docs/CONNECTIONS.md` section 8.

## The SDK

Official `mcp` Python SDK, MIT. PyPI and https://py.sdk.modelcontextprotocol.io/ say v2 is the current stable line (2.0.0 on 28 Jul 2026, 2.3.0 on 2 Oct 2026); v1 (last 1.30.0, 7 Sep 2026) is security and critical fixes only. We pin `mcp==2.3.0` (`services/agent/pyproject.toml`).

What we use (read from the installed 2.3.0 source, then confirmed against a fake server of ours): `mcp.Client(server, read_timeout_seconds=, cache=None, client_info=)` where the server is a `StdioServerParameters` (the SDK starts the process, merges `env` over a default environment, and ends the process tree on exit) or a `streamable_http_client(url, http_client=httpx2.AsyncClient(headers=...))` transport; `list_tools()` (paged), `call_tool(name, arguments, read_timeout_seconds=)` returning `CallToolResult` with `content`, `structured_content` and `is_error`; `MCPError` with `code` (`CONNECTION_CLOSED` -32000, `REQUEST_TIMEOUT` -32001); the server side `mcp.server.mcpserver.MCPServer` with `@tool(annotations=ToolAnnotations(...))`, `add_tool` and `run("stdio" | "streamable-http")` for our stand-ins and test servers.

Things we learned the hard way: `StdioServerParameters.env` is merged over `get_default_environment()` (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`), so keeping the child environment minimal means narrowing `mcp.client.stdio.DEFAULT_INHERITED_ENV_VARS`; a `Client` keeps anyio cancel scopes open for the whole session, so a connect timeout cannot be a `with fail_after(...)` around it (it is a watchdog that cancels the owning task); a server that dies mid-call surfaces as `MCPError(CONNECTION_CLOSED)`, not as an OS error; FastAPI in this repo wraps included routers in `_IncludedRouter` objects (look at `original_router.routes`); MCP tool annotations arrive on `Tool.annotations` as hints (`read_only_hint`, `destructive_hint`) from the server, which can lie.

## The servers

The official registry (https://registry.modelcontextprotocol.io/v0/servers?search=...) is a name-substring search capped at 30 results; absence is only proven with an owner search or a 404 on `/v0/servers/<name>/versions/latest`. Several of the best servers are not in it (Git, Filesystem, Slack, Jira, Jupyter). The MCP project's own reference servers for GitHub, GitLab, Slack, Sentry, SQLite, PostgreSQL and Google Drive were archived on 29 May 2025 and their npm packages are deprecated; the maintained replacements are the vendors' own (GitHub, Sentry, Google's MCP Toolbox) or community servers. Hosted vendor servers (Linear, Atlassian, Slack, Notion, Google Workspace, Microsoft Work IQ) were not shipped: no package to pin, no LICENSE file to read, or an approval gate; see the unverified table.

## What we took, in our own words

The idea of a registry entry with a pinned package and launch command (our manifest has the same facts but is checked by our validator); the SDK's client API; the Clicky plugin manifest conventions already recorded in `clicky-reuse.md`. We copied no code from any server or from the SDK. We did not use Composio, Nango or any hosted aggregator: the worker's data would leave the device.
