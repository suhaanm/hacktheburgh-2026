#!/usr/bin/env bash
# Checks the build machine. Never prints secret values.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

ok()   { printf "  [ok]   %s\n" "$1"; }
warn() { printf "  [warn] %s\n" "$1"; }
bad()  { printf "  [FAIL] %s\n" "$1"; FAILED=1; }
FAILED=0

echo "Tools"
for t in git gh node npm python3 uv; do
  if command -v "$t" >/dev/null 2>&1; then ok "$t: $($t --version 2>&1 | head -1)"; else
    if [[ "$t" == "uv" ]]; then warn "uv not found (install it; spec expects Python 3.12 via uv)"; else bad "$t not found"; fi
  fi
done
if command -v python3 >/dev/null 2>&1; then
  v="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  [[ "$v" == "3.12" || "$v" == "3.13" ]] && ok "python3 is $v" || warn "python3 is $v; use Python 3.12 via uv for the services"
fi
[[ "$(uname)" == "Darwin" ]] && ok "macOS detected" || warn "not macOS: the desktop actuator and off-hours run are macOS-first"

echo "Environment (.env)"
[[ -f "$ROOT/.env" ]] && ok ".env present" || bad ".env missing (copy .env.example)"
if [[ -n "${ALONGSIDE_PATH:-}" && -f "${ALONGSIDE_PATH}/package.json" ]]; then ok "ALONGSIDE_PATH points at a project"; else bad "ALONGSIDE_PATH unset or not a project directory"; fi
[[ -n "${OPENAI_API_KEY:-}" ]] && ok "OPENAI_API_KEY is set (value hidden)" || bad "OPENAI_API_KEY is not set"
[[ -n "${OPENAI_MODEL_PLANNER:-}" ]] && ok "OPENAI_MODEL_PLANNER set" || warn "OPENAI_MODEL_PLANNER unset (decide in spike S1)"
[[ -n "${OPENAI_MODEL_COMPUTER_USE:-}" ]] && ok "OPENAI_MODEL_COMPUTER_USE set" || warn "OPENAI_MODEL_COMPUTER_USE unset (decide in spike S1)"

echo "Repo"
[[ -d "$ROOT/references" ]] && ok "references/ present" || warn "run scripts/clone-references.sh"
git -C "$ROOT" check-ignore -q .env && ok ".env is gitignored" || bad ".env is NOT gitignored"

echo
if [[ "$FAILED" -ne 0 ]]; then echo "Some checks failed."; exit 1; else echo "Environment looks usable."; fi
