# Connections: curated plugins and MCP servers

> Knack can be connected to the apps a worker already uses, from a short curated list for their role. Every connection starts off and read-only; reads are allowed, every change waits for a click.

**Capability:** Connections and MCP plugins · **Status:** landing · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** landing (owner decision D55; built and documented on the CONNECTIONS branch (worktree-agent-a2c1788e3e4c0c876, docs/CONNECTIONS.md at 00:38 UTC); not on main yet; nothing real has been connected) · **Page:** `docs/features/connections.md` · **Targets:** Wordsmith

## What it does

Knack can read from the apps a worker already uses through servers that speak the Model Context Protocol (MCP), the open standard for letting an assistant use an app's tools. There are 15 chips in three sets (Dev, Data, Benefits). Every chip starts off, reading is allowed, every change waits for the worker's own click, and deleting or running code is always a person's call.

## How it works

Knack writes no connectors. It reuses the official MCP Python SDK (version 2.3.0, pinned exactly, MIT) and the servers that GitHub, Google, Sentry and the community already publish, each pinned to one verified version; the repository's own plugin framework carries them. Hosted aggregators are not used, because the worker's data would leave the device through a third party. The consent line names who publishes the server, the package and version, the hosts it talks to and 'with your token' or 'It stays on this Mac'; a hash of what would run is stored with the consent, so a changed manifest disables the connection until the worker confirms again. Versions are exact (never 'latest'), launched with no shell, install scripts off and a minimal environment. Our own per-tool table decides what a call is; a server's own read-only hints never lower a class; SQL counts as a read only when code reads one read-only statement. A write or a send becomes an outward approval and a delete or code run an irreversible one, each bound to a digest of the arguments, used once, and expiring; inside a child agent nothing is ever opted in. An unattended run may read, and only for a connection the worker opted that very routine into. A tool result is data: it passes the injection detector, and in menu mode no model sees the text. Tokens go into the macOS Keychain on standard input, never in the repository, a log, a prompt, the dashboard or the ledger. Every call leaves a row written before the call (no row, no call) with sizes and outcome, never arguments or results. The worker's denylist and the kill flag apply. No screen or file lets the worker add an arbitrary server.

**What is different.** The list is curated and read-only by default, starts off, and avoids hosted aggregators so data does not leave the device.

## Where to see it

First run, inside the role card: 'Connect your tools' chips for the chosen role, all off; a click shows the consent lines and only Connect connects, and the chips connect the Example version only, no account. Settings, Connections: the full list in three sets with Connect, Revoke, a Real choice that asks for a folder or address and a token, and counts of what each has read. Dev: GitHub, Git, Jira, Slack, Sentry, Files. Data: SQLite, Postgres, BigQuery, Sheets and Drive, Jupyter, Notion, Slack. Benefits: Outlook calendar, Teams meetings (meeting times and counts only), SharePoint. Chips carry printed flags: Notion 'Vendor says unmaintained', Sentry 'Source-available licence', and 'Community server' on Slack, Jira, Jupyter, Sheets and Drive and SharePoint.

## Demo moment

In first run choose Programmer and connect the Example GitHub (an invented repository). Ask what is waiting: it reads three open issues; a comment it drafts waits for a click and a merge is a person's call. Or connect Example SQLite: one SELECT runs, a DELETE stops at the queue marked irreversible. Open Settings, Connections to show the counts and Revoke.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| Engine: manifests validate and are verified with sources; floating versions, shells, mounted volumes, tools in two classes and secret-looking variables are refused; the command hash changes with anything that would run; consent, reconfirm, revoke, routine opt-in; the token store; metadata-only ledger rows; the routes | offline tests (53 test functions on the engine side) | `docs/CONNECTIONS.md (section 9); services/engine/tests/connections/ (branch)` |
| Agent: through the real SDK client against our stand-ins and a hostile test server that lies about its tools, hangs, crashes, floods and shows its environment: classification, minimal environment, restarts, timeouts, the size cap, no sampling or questions to the worker, refusal for destructive and execute without a click and in an unattended run; a poisoned tool result pauses the child | offline tests with stand-ins; no real server started | `docs/CONNECTIONS.md (section 9)` |

## Honest limit

Not on main, so not verified by the lead. Nothing real was connected: the real launches (npx, uvx, docker at the pinned versions) are verified from their sources and unit-tested as command lines only. A connected server's own traffic goes from its process to its own hosts and is outside the frame egress guard (the panel and the ledger say so); Knack never sends a screen frame or page text through a connection. Linear, named in D55, is not shipped: Linear's official server is hosted only with no package or licence file to read, so Jira is shipped instead; Slack's, Atlassian's and Google's own hosted servers are also listed as not shipped. The curated list is chosen by a person in the repository; a new preset needs its source verified first.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a workflow that crosses apps and servers, kept read-only, consented and local by default

## 30-second spoken script

> Knack can connect to the apps you already use, from a short curated list for your job, using the open MCP standard. Everything starts off and read-only. Reading is allowed; every change, like a comment or a deleted row, waits for your click, and deleting and running code are always your call. In the demo each one points at a stand-in with invented data, so no real account is touched. If what would run changes, Knack asks you again. This is landing now and not yet verified by us on the main build.

## Slide bullets

- 15 chips in three sets for Dev, Data and Benefits; all start off and read-only.
- MCP servers reused at one verified version each; no connectors written; no hosted aggregators.
- Our table decides every call; a server's hints never lower a class; changes wait for a click.
- Tokens in the Keychain; a row in the ledger before every call, never the content.
- Landing: nothing real connected; Linear and several hosted servers not shipped.

## Sources

- `docs/CONNECTIONS.md (branch worktree-agent-a2c1788e3e4c0c876)`
- `docs/DECISIONS.md (D55)`
- `docs/IMPLEMENTATION_SPEC.md (14.4)`
- `services/engine/understudy_engine/connections/ and services/agent/understudy_agent/connections/ (branch worktree-agent-a2c1788e3e4c0c876)`
- `packages/connections/presets/ (branch worktree-agent-a2c1788e3e4c0c876)`

## Related pages

`role-packs.md`, `knack-shell.md`
