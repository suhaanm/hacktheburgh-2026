# Rouge (no licence: ideas only) - notes for `completion.py` (AGT-4)

**What it does well.** Before the agent may say "done", code inspects the final observation (page text plus accessible element names) for the tokens the goal asked for; if the observation is empty or the tokens are absent, the claim is replaced by "I could not verify". Blocker language ("couldn't", "unable") is allowed through as an honest failure, not a success. A repeated failing action signature stops the loop instead of retrying. Fields that must never be read (password, card, account, ids, one-time codes) live in a JSON data file, matched on word lists after splitting camelCase and punctuation, and only for text-entry control types.

**What informs us.** AGT-4 (code decides success; a model "done" that fails the check is a false claim), CAP-4 (sensitive fields as data; the repo already has `packages/schema/sensitive_fields.json`), and the repeated-failed-action guard in navigators.

**What we do differently.**
- Our goal tokens are structured, not regex over free text: each calculator must show named result fields with the numeric values we expect from its page schema, plus the case-note id. The check runs on a *fresh* observation taken after the final step.
- A `CompletionResult(ok, missing, false_claim)` is returned; `false_claim` is true exactly when a model claimed success and `ok` is false. Counts surface in the Agent API.
- We never relax the check for "navigation-style" goals. No heuristics based on goal wording.
- Sensitive-field filtering is done by the security track; navigators only consult `sensitive_fields.json` when extracting.

## Security track notes (agent-safety): `security/sensitive.py`, prompts, reader

- **Sensitive fields as data, enforced in code.** Rouge keeps its never-read fields in a JSON file and decides in code, before any screenshot, whether the control under the pointer is a secret field. Only names and the control kind are read, never the typed value. We do the same with `packages/schema/sensitive_fields.json`: the matcher splits camelCase and punctuation, and a plain button called "Password" is not a password field (only text-entry kinds count).
- **Prompts are not the boundary.** Its prompts say that window text, pages and results are untrusted data, and the code does the enforcing. Our version is the same split: the wording in a prompt is a courtesy; layers 1 to 8 are code.
- **Different from us.** Rouge has no quarantined reader and no taint tracking. We add both (layers 2 and 5), and measure them in the red-team ablation.
