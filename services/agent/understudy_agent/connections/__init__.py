"""Connections, agent side (CONNECTIONS): the MCP client runner, the call gate and the ``mcp_call`` runtime tool.

``classify`` decides what a call is (our table and verb rules; a server's own hints never lower a class), ``runner`` starts and talks to a connected
server with the official MCP SDK, ``service`` makes every refusal and every call (ledger row first, never arguments or results), ``hook`` is the
``mcp_call`` tool for ``runtime/tools.py``, and ``routes`` lets the engine ask this service to start or stop a connection the worker clicked.

Nothing here starts a process at import or at boot. See docs/CONNECTIONS.md.
"""
