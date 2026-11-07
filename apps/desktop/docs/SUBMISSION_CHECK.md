# Submission check

Run `npm run submit-check` (full: typecheck, vitest, build, about 2-5 min) or `npm run submit-check -- --fast` (skips those three). Exit code is non-zero on any FAIL. It never prints secret values.

| Check | PASS means | Notes |
|---|---|---|
| `.env` ignored and untracked | `git check-ignore .env` is true, nothing named `.env*` (other than `.env.example`) is tracked | |
| No secrets | The values of every `*KEY/TOKEN/SECRET*` var in `.env` appear in no tracked file, in `HEAD`, or in any commit (`git log --all -S`); no key-shaped strings (`AIza...`, `sk-...`, `ghp_...`, private-key blocks) in tracked files | WARN if `.env` is absent (shape scan only). A history hit needs a key rotation, not just a delete |
| No build dirs tracked | nothing under `node_modules/`, `out/`, `dist/` | |
| No file over 2 MB | all tracked files are under 2 MB | Allowlist (in the script): `package-lock.json`, `assets/showtime/clips/` |
| typecheck / tests / build | exit 0 | Skipped with `--fast` (WARN) |
| README sections | overview, setup/quickstart, architecture, trust/safety, limitations, credits/licensing, team headings exist | |
| LICENSE | file exists | Missing is a WARN: the user decides (README suggests MIT) |
| THIRD_PARTY_NOTICES | every file with an `Adapted from` header is named (path or basename) in the notices | FAIL means add the file to the notices |
| README references | relative links and backticked repo paths exist | |
| Repo visibility | `gh repo view` says PUBLIC | PRIVATE or no `gh` is a WARN: the user must decide before submitting |
| Demo stage + showtime | `apps/demo-stage/*`, `scripts/stage-server.mjs`, `assets/showtime/script.json` exist; `assets/showtime/clips/` is non-empty | Empty clips is a WARN |

Red items are fixed by the owning lane (see `orchestration/outbox.md`). WARN items are decisions for the user, not bugs.
