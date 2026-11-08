# Connections: curated plugins

> Apps, sites and MCP servers the worker can connect, chosen from a short curated list shown for their role, off until clicked and read-only by default.

**Capability:** Connections and MCP plugins · **Status:** landing · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** landing (owner decision D55; the engine side and the agent side are committed on the CONNECTIONS branch (worktree-agent-a2c1788e3e4c0c876, 00:14 UTC); docs/CONNECTIONS.md has not been seen on any branch) · **Page:** `docs/features/connections.md` · **Targets:** Wordsmith

## What it does

A worker can connect a few tools Knack may read from, from a short curated list that depends on their role. Every connection starts off and read-only, one click turns it on, and one click forgets the token and stops it.

## How it works

Each preset is a validated manifest (kind mcp) with two modes. Example uses a stand-in server of ours (a local folder, a SQLite file holding the synthetic dataset, a fake GitHub and a fake Slack, plus fixtures); Real names a verified publisher, package, pinned version, hosts and the credential names. Nothing is on until the worker confirms; there is no default, and no auto-connect in mock mode, tests, demos or first run. The consent is pinned to a hash of what would run (launcher, arguments, pinned version, hosts, credential names, or the stand-in script); if the manifest changes, the connection says it needs reconfirming and nothing starts until the worker confirms again. Our own table classes every known tool as read, write, send, destructive or execute and decides every call; a vendor's read-only switch is used as well where the server has one, and any write needs a click. A routine may use a connection unattended only if the worker opted that routine in for that connection, reads only. A token is entered by the worker once, goes to the macOS Keychain (through standard input, never an argument) or a mode-600 file, and is never in the repository, a log, a prompt, the dashboard or the ledger. The ledger rows hold counts only (calls, reads, changes asked, refused, bytes returned, tools used). There is no route that adds a server. Knack uses the official MCP Python SDK (MIT) as the client and does not use hosted aggregators, because data would leave the device. On the agent side, a tool's class comes from our table and verb rules and a server's own hints never lower it: an unlisted tool is refused or treated by its verb, a name nothing recognises is treated as a write, SQL counts as a read only when code reads one read-only statement, everything but a read needs a person's real click, and destructive and execute tools can never be opted in. A server process starts only for a switched-on connection after the hash check, at the pinned version with no shell, install scripts off and a minimal environment (the path, the home folder, fixed variables, the worker's own values and the one token). The client answers none of a server's own requests (no sampling, no questions to the worker), caps a result at 64 KB and hands it back as untrusted text, bounds every connect, call and stop with a timeout, and restarts a crashed server at most three times in ten minutes. The ledger row is written before the call and never holds arguments or results.

**What is different.** The list is curated and read-only by default, starts off, and avoids hosted aggregators so data does not leave the device.

## Where to see it

Settings has a Connections panel and first run has a presets slot under the role card (both are slots on main; the panel is landing). Presets by role, from the pack files on the branch: Programmer (GitHub, local Git, Jira, Slack, Sentry, filesystem); Data analyst (SQLite, Postgres, BigQuery, Google Workspace, Jupyter, Notion, Slack); Benefits processor (Outlook, Teams, SharePoint). Linear, named in D55, is not among the 13 preset files seen.

## Demo moment

In first run choose Programmer; the Dev preset appears with everything off. Connect the Example GitHub: it reads the stand-in only, the screen says read-only, and the record of what was read shows counts and no content. Revoke it.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| The engine side is covered by 53 test functions on the branch (18 manifest, 14 routes, 21 state); the agent side and the panel are not verified here | offline tests, on a branch, not on main | `services/engine/tests/connections/ (branch worktree-agent-a2c1788e3e4c0c876)` |

## Honest limit

Not on main, so not verified. Written from owner decision D55, the preset files and the engine code on the branch; check docs/CONNECTIONS.md when it lands. Real mode has not been exercised and no real account is used in the build or the demo; real Outlook, Teams or SharePoint access needs the owner's approval at run time (D26). Some real presets need Docker or npx. Custom servers are out of scope by decision.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a workflow that crosses apps and servers, kept read-only, consented and local by default

## 30-second spoken script

> Knack can connect to a short, curated list of tools, and everything starts off and read-only. Pick a role and you see the set for that job: developers get GitHub, Git, Jira, Slack; analysts get databases and sheets; benefits processors get Outlook, Teams and SharePoint. In the demo each one points at a stand-in we wrote, so no real account is touched. A change to what would run needs your confirmation again. This is landing now and is not yet verified.

## Slide bullets

- Curated list per role; no arbitrary servers; each connection starts off and read-only.
- Example mode uses stand-ins we wrote; Real mode is the worker's own token, in the Keychain.
- Consent is pinned to a hash of what would run; a change asks again.
- Our table classes every tool and decides every call; any write needs a click.
- Landing: engine side on a branch; not yet on main.

## Sources

- `docs/DECISIONS.md (D55)`
- `docs/IMPLEMENTATION_SPEC.md (14.4)`
- `docs/REFERENCES.md (Marketplace plugin mapping)`
- `docs/CONNECTIONS.md (landing)`
- `services/engine/understudy_engine/connections/ and services/agent/understudy_agent/connections/ (branch worktree-agent-a2c1788e3e4c0c876)`
- `packages/connections/presets/ (branch worktree-agent-a2c1788e3e4c0c876)`

## Related pages

`role-packs.md`, `knack-shell.md`
