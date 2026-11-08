# Connections: plugins, apps and MCP servers (CONNECTIONS)

Owner request, 7 Nov 2026, 23:20 GMT. Branch of record: `worktree-agent-a2c1788e3e4c0c876`. Every claim below is checked by a test or comes from a source URL listed in section 8. Where something is not verified it says so.

## 1. What it is, in one paragraph

Knack can be connected to the apps a worker already uses: GitHub, Git, Jira, Slack, Sentry and a folder for a programmer; SQLite, Postgres, BigQuery, Sheets and Drive, Jupyter, Notion and Slack for a data analyst; Outlook and Teams meeting times and SharePoint for a benefits processor. A connection is a small program that speaks the Model Context Protocol (MCP), the open standard for letting an assistant use an app's tools. Knack does not write a connector for each app: it reuses the official MCP Python SDK and the servers that GitHub, Google, Sentry and the community already publish, pinned to one exact version each. Every connection starts OFF and read-only. The worker turns one on with a click on a chip, after reading what it will do. Reading is allowed; every change (a comment, a post, a deleted row) waits for the worker's own click in the approval queue; deleting and running code are always a person's call. The demo uses local stand-ins with invented data (a folder, a small database, a fake GitHub, a fake Slack), badged **Example** everywhere, so nothing real is touched.

## 2. Why MCP, and what we reused

| Decision | What we chose | Why (source) |
|---|---|---|
| Protocol | MCP, the open standard | One way to reach many apps; servers already exist and are maintained by the app vendors and the community |
| Client library | Official `mcp` Python SDK, **2.3.0, pinned exactly** (MIT), a dependency of `services/agent` | PyPI and the SDK docs call v2 "the current stable release line" (2.0.0 on 28 Jul 2026, 2.3.0 on 2 Oct 2026); `pip install mcp` now installs 2.x; the 1.x line (last 1.30.0) gets security and critical fixes only; the real servers we checked already require it (`mcp-server-git` needs `mcp>=2.3,<3`, `jupyter-mcp-server` needs `mcp>=2,<3`). We use `Client` with stdio and streamable HTTP. If 2.x ever misbehaves, `mcp>=1.30,<2` is the fallback: the runner uses only `Client`, `StdioServerParameters` and `call_tool`. |
| Servers | Existing ones, one per app, pinned to an exact version, verified from the source (section 8) | We write no connectors. We wrote only five tiny stand-ins for the demo |
| Plugin framework | The repo's own PLG-1 framework (`services/engine/understudy_engine/plugins`), extended with `kind: mcp` and a meaning for `kind: tool` | One framework, not two. The read-only calendar sources (Outlook, Teams) stay sources and are offered as chips too |
| Manifest style | Clicky's Windows fork conventions (plugin.yaml, schemas), MIT, summarised in `docs/reference-notes/clicky-reuse.md` | Conventions only; nothing copied |
| Not used | Hosted aggregators (Composio, Nango and similar) | The worker's data would leave the device through a third party |

## 3. The presets

All start OFF. "Example moment" is a line for the pitch or the launch video, played with the local stand-ins.

| Chip | Set | What it reads | Example moment for the video |
|---|---|---|---|
| GitHub | Dev | Issues, pull requests, commits and code the worker can already see | "What is waiting on me?" The agent reads three open issues. A comment it drafts waits for a click, and a merge is a person's call |
| Git | Dev | Commits, diffs and branches of one local repository | The habit insight names the last five commits it read, on this Mac |
| Jira | Dev | Issues, boards and sprints | The sprint board is read; moving a ticket stops at the queue |
| Slack | Dev, Data | Channels, threads and people | Unreads in the claims channel are read; "Send" needs the click |
| Sentry | Dev | Errors, traces and releases | The week's top error group is read; resolving it waits |
| Files | Dev | One folder the worker picks | Today's stand-up note is read from the folder; writing a file waits |
| SQLite | Data | Tables and rows in one database file | One `SELECT` runs; a `DELETE` stops at the queue and is marked irreversible |
| Postgres | Data | One database | The same, with a read-only role |
| BigQuery | Data | Datasets and tables | The same, with the server's read-only switch on |
| Sheets and Drive | Data | Spreadsheets and Drive files | October's totals are read from a sheet |
| Jupyter | Data | Notebooks and cells in the worker's own JupyterLab | The review notebook is read; running a cell is always a click |
| Notion | Data | Pages and databases shared with an integration | The team handbook page is read. The chip says "Vendor says unmaintained" |
| Outlook calendar | Benefits | Meeting times and counts only, no titles, no people | "Meeting hours this week" appears as a number |
| Teams meetings | Benefits | Meeting times, length and attendance counts | The same, for Teams |
| SharePoint | Benefits | Sites, lists and document libraries | The guidance library is listed; adding a row waits |

Where they appear: **first run**, inside the role card, "Connect your tools" chips for the chosen role (every chip off; a click shows the consent lines; only **Connect** connects; the chips connect the Example version only, no account). **Settings, Connections**: the full list in three sets, with Connect, Revoke, a Real choice that asks for the folder or address and the token, and counts of what each has read.

Outlook and Teams are Example only in the app: they are the calendar layer's read-only Graph sources, and a real sign-in to a Microsoft account is set up by the owner for a specific approved run (D26), never from a button here.

Chip flags, printed on the chip itself: Notion "Vendor says unmaintained"; Sentry "Source-available licence"; Slack, Jira, Jupyter, Sheets and Drive, SharePoint "Community server".

## 4. The security model, in plain words

1. **Off until clicked.** A missing record means off. No connection starts in mock mode, in a test, in a demo, at first run or at boot, and an unattended run cannot switch one on. Nothing is started by Knack for a real server except after the worker's own click.
2. **The consent line names everything.** Before the click it says who publishes the server, which package and which pinned version, which hosts it talks to, and "with your token" (or "with your own sign-in", or "It stays on this Mac"), that any change needs a click, and that it can be revoked any time. The engine writes those lines from the manifest; the page cannot change them.
3. **What would run is pinned.** A hash of the launcher, arguments, pinned version, hosts and credential names (for a stand-in, of every stand-in file) is stored with the consent. If the manifest or a stand-in changes, the connection is disabled (`needs_reconfirm`) until the worker confirms again.
4. **Exact versions only.** Never `latest`, never a range. `npx` launches with `-y` and install scripts switched off (`npm_config_ignore_scripts=true`); `uvx` with `UV_NO_BUILD=1` (wheels only); `docker` is `run -i --rm image:<pinned version>` with no mounts or published ports. No shell is ever used.
5. **A minimal environment.** The server process gets `PATH` and `HOME`, the manifest's fixed variables (for example a documented read-only switch), the worker's own values for that connection and the one token. Nothing inherited from Knack or from another connection.
6. **Our class wins.** MCP tool annotations (`readOnlyHint`, `destructiveHint`) are hints from an untrusted process. The class of a call is decided by our per-tool table in the manifest and verb rules (reusing the word lists of `security/labels.py`). A hint can raise the class of a tool we do not list, never lower any class. A server that marks `delete_everything` read-only still gets a click, shown as a delete. `execute_sql` is decided by our code reading the statement: one read-only statement is a read; a second statement, `DROP`, an `INTO`, a side-effect function or anything odd is not. A `method: delete` argument turns any tool destructive. A preset can say `unlisted: refuse`: a tool outside its table is never called (SharePoint's server has hundreds of mail and calendar tools that are outside its consent).
7. **Reads allowed, changes ask.** A read runs. A write or a send becomes an outward approval item, a delete or a run-code an irreversible one, each needing a real click on this exact call (the approval is bound to a digest of the arguments, is used once and expires). Delete and execute can never be opted in. Inside a child agent the rung is always A0 and nothing is opted in, so there is no way to skip the click.
8. **Away from the keyboard: reads only.** An unattended run may read, and only for a connection the worker opted that very routine into. A write, a send, a delete or a code run is refused even if something else approved it.
9. **A tool result is data.** It goes through the injection detector and, in raw mode, the quarantined reader, and enters a prompt only as checked fields. In menu mode no model sees the text at all. We never set sampling, elicitation or roots callbacks, so a server cannot make a model of ours run for it or ask the worker anything.
10. **Tokens.** Typed by the worker, once, into a password field. Stored in the macOS Keychain through the `security` command (the token goes in on standard input, never as an argument), or in a mode-600 file outside the repository if the Keychain is not the backend. Never in the repository, a log, a prompt, the dashboard, the ledger or an error message. Revoke is one click and a confirm: the token is forgotten, the process is stopped, every routine opt-in is removed.
11. **Every call leaves a metadata-only row** in the privacy ledger, written before the call (if it cannot be written the call is not made): server, tool name, class, size of the arguments, size of the result, outcome, time. Never the arguments, never the result. The Connections panel shows counts only.
12. **Where the traffic goes.** A connected server's own traffic goes from that server's process to its own hosts. It is outside the frame egress guard, which never sees a frame or page text from a connection. Knack never sends a screen frame or page text through a connection. This is stated in the panel and in the ledger.
13. **The worker's denylist applies**: a connection is refused if the denylist names its host or its app. The kill flag stops every call. A crashed server is restarted at most three times in ten minutes, then left off until the worker starts it.
14. **Curated only.** No route, screen or file format lets the worker add an arbitrary server. A new preset is added by a person, in the repository, after verifying it (section 6).

## 5. Where it lives

| Part | Path |
|---|---|
| Schemas | `packages/schema/connection.schema.json` (the connection block), `plugin.schema.json` (kind `mcp` and `tool`), `pack.schema.json` (`connections:`) |
| Presets | `packages/connections/presets/*.yaml` (13), plus a `connection:` block on the two Graph source manifests |
| Role lists | the `connections:` key at the end of each `packages/packs/<role>/pack.yaml` |
| Stand-ins | `packages/connections/standins/` (filesystem, SQLite, GitHub, Slack, and a fixture server for the rest) |
| Engine | `services/engine/understudy_engine/connections/` (registry, manifest, state, secrets, ledger, routes), flag `UNDERSTUDY_X_CONNECTIONS` (on by default, D48) |
| Agent | `services/agent/understudy_agent/connections/` (classifier, runner, service, `mcp_call` hook, routes) |
| Dashboard | `apps/dashboard/src/components/connections/` (`ConnectionChips`, `ConnectionsPanel`), `src/screens/Connections/` (model, client, example fixture) |
| Routes (engine) | `GET /connections`, `GET /connections/{id}`, `POST /connections/{id}/connect`, `/reconfirm`, `/revoke`, `/routines`, `GET /connections/{id}/reads` |
| Routes (agent) | `POST /connections/{id}/start`, `/stop`, `GET /connections/{id}/status`. There is deliberately no route that calls a tool |

## 6. How a new preset is added

1. Verify the server from its sources: the package exists at that exact version in its registry, the publisher is the repository owner, you read the LICENSE file, and the install method comes from the README or the official MCP registry (`registry.modelcontextprotocol.io`). If any of that fails, do not ship it: add it to the unverified list below.
2. Copy `packages/connections/presets/slack.yaml`, set the id, the one-line `reads` and the six-word `short`, the `standin` (a script and fixture under `standins/`), and `real` with the pinned version in the arguments, the environment variable names of the token, the hosts, the licence and at least two source URLs including the LICENSE file.
3. List every tool you know in `tools.classes` (read, write, send, destructive, execute). Choose `unlisted: refuse` if the server has a much bigger tool set than the consent covers. Use `classifiers: {tool: sql}` for a tool that runs a statement.
4. Add the id to the role pack's `connections:` list.
5. Run `uv run python -m understudy_engine.plugins validate` and `uv run python scripts/gen_connections_fixture.py`, then the tests. Validation refuses a floating version, a shell character, a secret-looking fixed variable, a tool in two classes and an unverified real mode.

## 7. What the owner must do for the real connections

Nothing here is needed for the demo. Each real connection is made by the owner in Settings, Connections, **Connect**, then **Real**. Knack never creates an account or an app for the owner.

| Chip | What to have ready |
|---|---|
| GitHub | Docker running; a fine-grained personal access token with read access to the repositories (contents, issues, pull requests, metadata) |
| Git | `uv` installed; the folder of one repository |
| Jira | `uv`; the site address, the account email and an Atlassian API token |
| Slack | Node; a user token (`xoxp-...`) from a Slack app with read scopes; not the browser-session option |
| Sentry | Node 22.15 or newer; a user auth token with read scopes. Do not give the server an LLM key |
| Files | Node 24 or newer; the folder |
| SQLite | Node; the database file |
| Postgres | Node; host, database, user and the password of a read-only role |
| BigQuery | Node; the project id; `gcloud auth application-default login` done once |
| Sheets and Drive | `uv`; a Google OAuth client id and secret you create; a browser sign-in on first use |
| Jupyter | `uv`; a JupyterLab you start yourself with a token, and its address |
| Notion | Node; an internal integration token with read access, with only the pages you want shared with it |
| SharePoint | Node; a Microsoft Graph access token (about an hour) and, in a work tenant, an administrator who allows the app |
| Outlook, Teams | the existing Graph sources (`UNDERSTUDY_GRAPH=1` and a token provider); the read-only, aggregate-only check on a real account needs the owner's approval of that specific run (D26) |

## 8. Licences and sources of every reused server (read 7 Nov 2026)

The SDK: `mcp` 2.3.0, MIT, https://pypi.org/project/mcp/ and https://github.com/modelcontextprotocol/python-sdk, docs https://py.sdk.modelcontextprotocol.io/.

| Preset | Server | Version | Publisher | Licence | Sources |
|---|---|---|---|---|---|
| Files | `@modelcontextprotocol/server-filesystem` (npm) | 2.2.0 | MCP project | Apache-2.0 and MIT | https://registry.npmjs.org/@modelcontextprotocol/server-filesystem/2.2.0, https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem, https://raw.githubusercontent.com/modelcontextprotocol/servers/main/LICENSE |
| Git | `mcp-server-git` (PyPI) | 2026.11.4 | Anthropic, PBC. (MCP project) | MIT | https://pypi.org/pypi/mcp-server-git/2026.11.4/json, https://github.com/modelcontextprotocol/servers/tree/main/src/git, https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/git/LICENSE |
| GitHub | `ghcr.io/github/github-mcp-server` (container) | 2.1.0 | GitHub | MIT | https://registry.modelcontextprotocol.io/v0/servers/io.github.github%2Fgithub-mcp-server/versions/latest, https://github.com/github/github-mcp-server/releases/tag/v2.1.0, https://raw.githubusercontent.com/github/github-mcp-server/main/LICENSE. The release v2.1.0 and the registry entry were read; the ghcr tag page was not |
| Jira | `mcp-atlassian` (PyPI) | 0.23.1 | sooperset, community | MIT | https://pypi.org/pypi/mcp-atlassian/0.23.1/json, https://github.com/sooperset/mcp-atlassian, https://raw.githubusercontent.com/sooperset/mcp-atlassian/main/LICENSE |
| Slack | `slack-mcp-server` (npm) | 1.3.0 | korotovsky, community | MIT | https://registry.npmjs.org/slack-mcp-server/1.3.0, https://github.com/korotovsky/slack-mcp-server, https://raw.githubusercontent.com/korotovsky/slack-mcp-server/master/LICENSE |
| Sentry | `@sentry/mcp-server` (npm) | 0.49.0 | Sentry (vendor) | **FSL-1.1-ALv2, source-available, not OSI** (becomes Apache-2.0 two years after each release) | https://registry.modelcontextprotocol.io/v0/servers/io.github.getsentry%2Fsentry-mcp/versions/latest, https://registry.npmjs.org/@sentry/mcp-server/0.49.0, https://raw.githubusercontent.com/getsentry/toolkit/main/LICENSE.md. We run the published package unmodified and copy no code |
| SQLite, Postgres, BigQuery | `@toolbox-sdk/server` (npm), Google's MCP Toolbox | 1.16.0 | Google (googleapis) | Apache-2.0 | https://registry.modelcontextprotocol.io/v0/servers/io.github.googleapis%2Fmcp-toolbox/versions/latest, https://registry.npmjs.org/@toolbox-sdk/server/1.16.0, https://raw.githubusercontent.com/googleapis/mcp-toolbox/main/LICENSE |
| Sheets and Drive | `workspace-mcp` (PyPI) | 2.3.0 | Taylor Wilsdon, community | MIT | https://registry.modelcontextprotocol.io/v0/servers/io.github.taylorwilsdon%2Fworkspace-mcp/versions/latest, https://pypi.org/pypi/workspace-mcp/2.3.0/json, https://raw.githubusercontent.com/taylorwilsdon/google_workspace_mcp/main/LICENSE |
| Jupyter | `jupyter-mcp-server` (PyPI) | 2.2.4 | Datalayer, community | BSD-3-Clause | https://pypi.org/pypi/jupyter-mcp-server/2.2.4/json, https://github.com/datalayer/jupyter-mcp-server, https://raw.githubusercontent.com/datalayer/jupyter-mcp-server/main/LICENSE |
| Notion | `@notionhq/notion-mcp-server` (npm) | 2.6.1 | Notion (vendor) | MIT | https://registry.npmjs.org/@notionhq/notion-mcp-server/2.6.1, https://github.com/makenotion/notion-mcp-server, https://raw.githubusercontent.com/makenotion/notion-mcp-server/main/LICENSE. The repository says it is no longer actively maintained and may be sunset |
| SharePoint | `@softeria/ms-365-mcp-server` (npm) | 0.171.0 | Softeria, community | MIT | https://registry.modelcontextprotocol.io/v0/servers/io.github.Softeria%2Fms-365-mcp-server/versions/latest, https://registry.npmjs.org/@softeria/ms-365-mcp-server/0.171.0, https://raw.githubusercontent.com/Softeria/ms-365-mcp-server/main/LICENSE |
| Outlook, Teams | our own Graph source adapters (`graph_outlook`, `graph_teams`), read-only, aggregate-only | 0.1.0 | this repository | this repository | https://learn.microsoft.com/en-us/graph/api/user-list-calendarview, https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list |

How it was verified: two read-only research passes on 7 Nov 2026 (the MCP registry API, npm and PyPI JSON, GitHub's API and raw files), nothing installed or run. This track re-read `@modelcontextprotocol/server-filesystem` 2.2.0 and `mcp-server-git` 2026.11.4 against npm and PyPI itself, and the lead checked that `mcp` 2.3.0 exists on PyPI (MIT, uploaded 2 Oct 2026). Versions were published between 2 weeks and hours before the check; the pin is the version that was verified, and Knack asks the worker to confirm again if a pin ever changes. No server was installed or run during this work: all tests use our own stand-ins and a hostile test server written with the SDK.

### Unverified: listed, not shipped

| App | What exists | Why it is not shipped |
|---|---|---|
| Linear | Linear's official hosted server, `https://mcp.linear.app/mcp` (also `/mcp/readonly`), registry entry `app.linear/linear` 1.0.2 | Hosted only: no package, no repository, no LICENSE to read, and the tool list is only visible after an OAuth sign-in. Jira is shipped instead |
| Atlassian (Jira) | Atlassian Rovo MCP Server, hosted, `com.atlassian/atlassian-mcp-server` 2.0.0 | Hosted only, no package version to pin; the community `mcp-atlassian` is shipped |
| Slack | Slack's own hosted server, `https://mcp.slack.com/mcp` | Only directory-published or internal apps may use it; tool names are not published. The community server is shipped. `@zencoderai/slack-mcp-server` is stale (0.0.1) with a mixed licence |
| Microsoft 365 | Work IQ MCP (hosted `https://workiq.svc.cloud.microsoft/mcp`, and `npx @microsoft/workiq`); the legacy `com.microsoft/workiq-*` servers | Work IQ's licence is contradictory (repository file MIT, npm "SEE EULA", Learn "proprietary") and needs tenant admin consent; the legacy servers are marked not for new projects. Outlook and Teams use our Graph sources; SharePoint uses Softeria |
| Google | Hosted BigQuery (`bigquery.googleapis.com/mcp`), Drive and Sheets (`drivemcp`, `sheetsmcp`) servers | Hosted, Developer Preview, no package. Toolbox and `workspace-mcp` are shipped |
| Notion | Notion's hosted `https://mcp.notion.com/mcp` | Browser OAuth, no package or licence file. The local server is shipped with its warning |
| Postgres | `crystaldba/postgres-mcp` 0.3.0 | Last release May 2025; it depends on an unpinned `mcp` and would likely break on 2.x; its PyPI page does not link its repository. Toolbox is shipped |
| Archived | The MCP project's reference servers for GitHub, GitLab, Slack, Sentry, SQLite, PostgreSQL and Google Drive; the npm packages `@modelcontextprotocol/server-github`, `-slack`, `-postgres` | Archived on 29 May 2025, marked deprecated, "no security guarantees" |
| Considered, not chosen | `bytebase/dbhub` 1.6.0 (MIT), an alternative for SQLite and Postgres; Softeria's Outlook and Teams tools | DBHub's read-only mode needs a TOML config; Toolbox covers three apps with one package. Outlook and Teams stay aggregate-only through the calendar layer |

## 9. What is tested

Engine: manifests validate and are all verified with sources; floating versions, shells, mounted volumes, tools in two classes and secret-looking variables are refused; the command hash changes when anything that would run changes; the consent names publisher, package, version, hosts and "with your token"; consent, `needs_reconfirm`, `needs_setup`, revoke, routine opt-in; the token store (mode 600, stdin-only Keychain command, all-or-nothing); metadata-only ledger rows; the routes and their write guard; the layer is registered and on by default.

Agent, through the real SDK client against our stand-ins and a hostile server that lies about its tools, hangs, crashes, floods and shows its environment: classification (our class wins, SQL reader, hidden delete), minimal environment, supervision and restart budget, timeouts, the size cap, stdio and loopback streamable HTTP, no sampling or elicitation or roots, refusal for an unconnected id, for destructive and execute without a click, and in an unattended run; the real SafetyPipeline and approval queue (an approval is for these arguments, used once); a poisoned tool result pauses the child and no model reads it.

Dashboard: the model, the client with and without the engine, the chips and the panel in a real DOM (every chip off, nothing connects without the click, the token is gone from the page, Revoke asks first), and the word budgets.

Not done: nothing real was connected, so no real server was started. The real launches (npx, uvx, docker with the pinned versions) are verified from their sources and unit-tested as command lines only.

## 10. How an agent role uses a connection

`mcp_call(connection, name, arguments?)` is the seventh runtime tool. A role uses it when its `RoleDef.allowed_tools` lists `mcp_call`. In the default menu mode the model never writes a call: the role's `Menu.calls` maps an id to `{connection, name, arguments}` (and the id is also a key of `Menu.files`), the model replies with the id, and code supplies the rest. `services/agent/tests/connections/test_runtime.py` registers one such role (`connector`) and runs it as a real child: a read finishes, a poisoned result pauses the child, a write waits in the queue, an unconnected id is refused, an unattended run reads only. No product role ships with `mcp_call` yet: a role that does is a decision for whoever owns that role, because every call it lists is something the worker's connection may be asked to do. In raw mode (a foreground run on something the worker named) the planner must be told which connection and tool to use; it has no catalogue of what the servers offer, on purpose, since a server's own words about its tools are untrusted.

## 11. What can be shown in the video today, and what cannot

Real and on screen now, with the local stand-ins and no account: the first-run role card with the "Connect your tools" chips for the chosen role (every chip off); a click on a chip printing the consent lines; **Connect** turning the chip on with the dashed **Example** badge; Settings, Connections with the three sets, the on-first order, the flags on Notion and Sentry, a connected row's counts line, and **Revoke** asking first ("Its token is forgotten and it stops."). The stand-in process really starts when a chip is connected (the Connections panel's "Not used yet" becomes counts once something reads) and really stops on Revoke.

Not shown by the product yet: an agent run that uses a connection. The runtime tool `mcp_call` and its approvals are built and tested (section 10), but no shipped agent role lists it, so nothing in the Needs-you screen is produced by a connection until a role does. The test role in `services/agent/tests/connections/test_runtime.py` is the worked example and can be turned into a shipped role in a few lines.
