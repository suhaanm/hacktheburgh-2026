# Eight security layers

> No allowlist: the agent may go anywhere. Eight layers, mostly code, stand between page content and any action.

**Capability:** Agents that do the work safely · **Status:** verified · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Eight security layers, approval queue and audit log, Optional sign-in step-up for irreversible approvals (Auth0).

## Eight security layers, approval queue and audit log

**Status:** verified · **Page:** `docs/features/security-layers.md` · **Targets:** Wordsmith

### What it does

Anything on a page that is written at an AI is treated as data, and the agent cannot act on it. Irreversible or outward-facing actions need a person's real click. There is no allowlist; the worker keeps an optional denylist.

### How it works

Layer 1 wraps everything from a page, screenshot, file or tool as untrusted data and strips invisible characters. Layer 2 is a quarantined reader: a model that sees raw content but returns only schema-checked fields, so the planner never sees raw text. Layer 3 is a fixed set of typed actions. Layer 4 is the action-class gate: send, post, submit, pay, delete, install or change permissions need a human click unless the worker opted that routine in. Layer 5 tags data with where it came from so tainted or personal data cannot be typed into a site the routine did not record. Layer 6 is an injection detector that pauses the run. Layer 7 is a goal-drift check plus a stuck-loop detector. Layer 8 protects settings: page content cannot change memory, the denylist, consent, quiet hours or the kill switch. Beside the layers sit an approval queue with evidence bundles, a hash-chained audit log, and local services that check the Host header on every request and the Origin on every write.

**What is different.** There is no allowlist. The gate classifies an action from the control that code reads under the pointer, not from the model's own label, and each layer's cost and benefit is measured by switching it off in turn.

### Where to see it

Needs you shows a paused run with 'Cannot be undone' printed; Your data shows what was sent; Evidence has the red-team tables.

### Demo moment

Open a page that carries hidden text aimed at an AI. The run pauses before the planner acts; the card in Needs you says the run paused and that nothing was changed, in content-free words.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Scripted red team: attack success 0.0% [0.0, 8.4] with every layer on, 100.0% [91.6, 100.0] with all layers off; false pauses on 31 clean pages 0.0% [0.0, 11.0] | synthetic, 42 attacks over 10 configurations, scripted planner | `evals/report.md (Red team with ablations)` |
| Real model: 0 of 126 runs let an attack through with every layer on; 5 of 126 (4.0% [1.0, 14.7]) with all layers off; the intervals overlap | real model, 42 cases x 3 repeats | `evals/report.md (Red team with a real model)` |
| Injected pages: the detector paused 20 of 20 runs before the planner acted; 0 attacks succeeded | real model (OpenAI), 20 households; pages carry text only | `evals/report.md (Agent runs on the sandbox)` |
| Two independent review passes by separate Claude agents (not human researchers): privacy and honesty, no critical finding and 6 high; real-actuator safety, 18 findings with 1 critical; reproducers pass 183 of 183 after fixes | owner-requested code review; fixes tested against fake desktops only | `evals/review/privacy_honesty.md; evals/review/safety_actuator.md; docs/MVP_STATUS.md` |

### Honest limit

The scripted planner follows any instruction, so the scripted table measures the layers, not a real model. In the real-model run the two intervals overlap: it shows what the layers cost (task success under attack 22% against 84%), not that they prevent attacks. We wrote both the attacks and the defences. The injected pages carry text only, so this shows the detector pauses, not that the gate resists hostile pages.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a browser agent that can be pointed anywhere and still cannot be steered by the page

## Optional sign-in step-up for irreversible approvals (Auth0)

**Status:** built (built; not configured: it needs the owner's Auth0 domain and client ID, and is never on the demo's critical path) · **Page:** `docs/features/security-layers.md` · **Targets:** Wordsmith

### What it does

When Auth0 is configured, approving something that cannot be undone, or that sends something outside this machine, needs a fresh sign-in, with the reason printed above the button. With no Auth0 values the app uses a local fallback and approves as before.

### How it works

A thin sign-in sits behind an interface with a local fallback. Items of risk class irreversible or outward need a step-up. A sign-in that was closed, is not recent enough, or is from a different account approves nothing and the item keeps waiting. Only a hash of the signed-in subject is returned to the engine. A real click is still required: signing in does not approve anything by itself.

**What is different.** Nothing new is claimed: a standard step-up sign-in placed on the irreversible step.

### Where to see it

Needs you, on an irreversible or outward approval row: 'Approving this cannot be undone, so we ask you to sign in again.'

### Demo moment

Not on the demo path. If configured, press Approve on an irreversible row: a sign-in opens first; close it and the row says nothing was approved.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| The step-up gate (when it applies, what each failure says, what is returned) is covered by unit tests | offline tests | `apps/dashboard/src/auth/gate.ts` |

### Honest limit

No tenant is configured, so the fallback approves as before. Never part of the P0 demo path. Not verified against a real Auth0 tenant.

### Hackathon target

- **Wordsmith (most complicated end-to-end browser-use workflow)**: a stronger gate on the irreversible step of an approval-gated agent

## 30-second spoken script

> Knack's agent can go anywhere on the web, so we do not rely on a list of safe sites. We rely on eight layers, almost all of them code. Page text is data, never instructions. A quarantined reader returns only checked fields. Anything irreversible waits for a real click. With every layer on, a scripted red team of forty-two attacks got through zero times; with all off, every time. In the real-model run the intervals overlap, and we say so.

## Slide bullets

- No allowlist; eight layers in code; optional denylist.
- Page content is data; a quarantined reader returns checked fields only.
- Irreversible actions need a real click; no key approves.
- Scripted red team: 0.0% with all on, 100.0% with all off (42 attacks).
- Real model: intervals overlap, so it shows cost, not proof.

## Sources

- `docs/IMPLEMENTATION_SPEC.md (section 9)`
- `README.md (Privacy and safety)`
- `evals/report.md (Red team with ablations, with a real model)`
- `evals/review/safety_actuator.md`
- `evals/review/privacy_honesty.md`
- `docs/MVP_STATUS.md`
- `docs/reference-notes/clickyyy.md`
- `docs/reference-notes/rouge.md`

## Related pages

`benefits-agent.md`, `stop-everything.md`, `computer-use.md`, `needs-you.md`
