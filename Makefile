# Targets are placeholders until the milestones in docs/IMPLEMENTATION_SPEC.md land.
# Replace each echo with the real command as it is built.
.PHONY: setup check refs demo eval test

setup:
	@echo "M0: install uv and Node, create the Python 3.12 environment, install workspaces. Not implemented yet."

check:
	@bash scripts/check-env.sh

refs:
	@bash scripts/clone-references.sh

demo:
	@echo "Runs the three-minute demo path in mock mode with wifi off (UNDERSTUDY_MOCK=1). Not implemented yet."

eval:
	@echo "Runs the evaluation suite and writes evals/report.json. Not implemented yet."

test:
	@echo "Runs pytest for services and vitest for apps. Not implemented yet."
