# Connections: curated plugins

> Apps, sites and MCP servers the worker can connect, chosen from a short curated list, off and read-only until enabled.

**Capability:** Connections and MCP plugins · **Status:** landing · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

**Status:** landing (owner decision D55; CONNECTIONS (Track E) is building it on its own branch; docs/CONNECTIONS.md has not landed) · **Page:** `docs/features/connections.md` · **Targets:** Wordsmith

## What it does

A worker can connect a few tools Knack may read from. Presets come with the role: a Dev set, a Data set and a Benefits set. Everything starts off and read-only; the list is curated, with no arbitrary servers.

## How it works

Knack uses the official MCP Python SDK (MIT) as the client and the repository's own plugin framework for sources; hosted aggregators are not used because the data would leave the device. Presets named by the owner: Dev (GitHub, Git, Linear or Jira, Slack, Sentry, Filesystem), Data (SQLite and Postgres, BigQuery, Google Sheets and Drive, Jupyter, Notion, Slack), Benefits (Outlook, Teams, SharePoint). Presets are offered inside the role card of first run, which adds one click (first run becomes four). The demo uses local stand-ins only: a local folder, a SQLite database with the synthetic dataset, and a fake GitHub and Slack we write. No real account is used.

## Where to see it

Settings has a Connections panel; first run shows the presets under the role card (both are slots on main; the panel itself is landing).

## Demo moment

In first run choose Programmer; the Dev preset appears, everything off. Switch on the local stand-ins; show the read-only badge and that nothing was sent.

## Evidence and its label

| What | Label | Source |
|---|---|---|
| The plugin framework for sources is covered by 41 test functions (static count); the connections panel itself has no evidence yet | offline tests; not verified for the new panel | `evals/report.facts.json (tests.by_dir, engine/plugins)` |

## Honest limit

Not on main. This entry is written from owner decision D55; check docs/CONNECTIONS.md when it lands. Real Outlook, Teams or SharePoint access has not been run and needs the owner's approval at run time (D26). Custom servers are out of scope by decision.

## Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a workflow that crosses apps and servers, kept read-only and local by default

## 30-second spoken script

> Knack can connect to a short, curated list of tools, and everything starts off and read-only. When you pick a role at first run you can choose a preset: a developer set, a data set, or a benefits set. For the demo they all point at local stand-ins we wrote, so no real account is touched. Custom servers are not allowed. This feature is landing now and is not yet verified.

## Slide bullets

- Curated list only; no arbitrary servers.
- Presets per role: Dev, Data, Benefits; all start off and read-only.
- Official MCP Python SDK as client; no hosted aggregators.
- Demo uses local stand-ins; no real accounts.
- Landing: not yet on main.

## Sources

- `docs/DECISIONS.md (D55)`
- `docs/IMPLEMENTATION_SPEC.md (14.4)`
- `docs/REFERENCES.md (Marketplace plugin mapping)`
- `docs/CONNECTIONS.md (landing, branch)`

## Related pages

`role-packs.md`, `knack-shell.md`
