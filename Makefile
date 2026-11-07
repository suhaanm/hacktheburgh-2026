# Understudy. Lead-owned. Services that do not exist yet are skipped by scripts/dev.sh.
# Python: `uv run --package <pkg>` (plain `uv run pytest` at the root does not see the service dependencies).
.PHONY: setup check refs synth dev stop demo preflight eval redteam test test-engine test-agent test-packs test-ui lint

UV_E = uv run --package understudy-engine
UV_A = uv run --package understudy-agent

setup:
	uv sync
	cd apps/dashboard && npm install
	@if [ -f extension/package.json ]; then cd extension && npm install; fi
	cd apps/desktop && npm install
	$(UV_A) playwright install chromium

check:
	@bash scripts/check-env.sh

refs:
	@bash scripts/clone-references.sh

# Deterministic synthetic personas and apprentices into data/synthetic (gitignored).
synth:
	$(UV_E) understudy synth --all

# Start engine (7700), agent (7710), sandbox sites (7801-7803) and dashboard (5173) in the background.
dev:
	@bash scripts/dev.sh

stop:
	@bash scripts/stop.sh

# The three-minute walkthrough: mock mode, no model calls, no network, isolated state (never your real ~/.understudy). Every extension layer is on (UNDERSTUDY_X=1). Run `make stop` first if a stack is already running.
demo:
	@mkdir -p data/demo-home data/demo-data
	@UNDERSTUDY_HOME=$(CURDIR)/data/demo-home UNDERSTUDY_DATA_DIR=$(CURDIR)/data/demo-data UNDERSTUDY_MOCK=1 $(UV_A) python -m understudy_engine.demo seed --reset
	@UNDERSTUDY_HOME=$(CURDIR)/data/demo-home UNDERSTUDY_DATA_DIR=$(CURDIR)/data/demo-data UNDERSTUDY_MOCK=1 UNDERSTUDY_X=1 bash scripts/dev.sh --open

# Plain green/amber/red readiness checklist (never prints secrets). `make preflight MODE=dev` relaxes the demo-only checks.
preflight:
	$(UV_A) python scripts/preflight.py --fix-hints --mode $(or $(MODE),demo)

# Writes evals/report.json and evals/report.md (the Evidence page reads them). Add FAST=1 for a quick run.
eval:
	UNDERSTUDY_MOCK=1 $(UV_A) python -m understudy_engine.eval $(if $(FAST),--fast,)

# Red-team ablation table (deterministic, offline, scripted vulnerable planner).
redteam:
	$(UV_A) python -m understudy_agent.security.redteam_runner

test: test-engine test-agent test-packs test-ui

# The agent environment is a superset of the engine's, and the engine API imports the agent's queue/audit/kill helpers.
test-engine:
	UNDERSTUDY_MOCK=1 $(UV_A) pytest services/engine/tests -q

test-agent:
	UNDERSTUDY_MOCK=1 $(UV_A) pytest services/agent/tests -q

test-packs:
	$(UV_E) python packages/packs/validate.py
	$(UV_E) pytest packages/packs/tests -q

test-ui:
	cd apps/dashboard && npm test --silent
	@if [ -f extension/package.json ]; then cd extension && npm test --silent; fi
	cd apps/desktop && ALONGSIDE_MOCK=1 UNDERSTUDY_MOCK=1 npm test --silent

lint:
	$(UV_E) ruff check services packages || true
