"""Connections (CONNECTIONS): curated plugins and MCP servers the worker connects with one click. Off until clicked, read-only by default.

The engine side: the curated list (``registry``, from ``packages/connections/presets`` and each role pack's ``connections:`` list), the manifest
and its checks (``manifest``), the worker's consent and the command-hash pin (``state``), the token store (``secrets``: Keychain or a mode-600
file), the metadata-only ledger rows and counts (``ledger``) and the routes (``routes``). The agent side, which starts the MCP processes and
decides every call, is ``understudy_agent.connections``. See docs/CONNECTIONS.md.

Importing the package pulls in nothing heavy and starts nothing.
"""
