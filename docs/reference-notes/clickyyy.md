# clickyyy (MIT; ideas re-implemented, no code copied) - notes for `security/drift.py`, `security/gates.py`, `security/labels.py`

**Stuck loops.** Every executed action is reduced to a canonical signature (what kind, which target or text, coordinates rounded into coarse buckets) so near-identical repeats compare equal and cosmetic fields such as a "reason" do not matter. The loop is "stuck" when the tail of the signature list is the same signature several times in a row, or a short cycle (period 2 to 4) repeated a few times. The run stops instead of burning its step budget.

**Destructive labels.** A deterministic regex over the label of a clicked element or menu item forces human approval for a short high-stakes verb list, regardless of what the model said. They deliberately left out "send/post/submit/save" to avoid training people to rubber-stamp. Sensitive-path patterns only warn; approval is the real gate.

**What informs us.** SEC-7 (stuck loop: same action 4x, or a 2 to 4 cycle 3x, as the spec says), SEC-4 (label classes feed the action-class gate), SEC-8 (the agent must not click protected controls).

**What we do differently.**
- Signatures round coordinates into 24 px buckets and ignore any model-written explanation; typed text is hashed into the signature, never stored.
- Our label classes are *classes* (submit, send, post, pay, delete, install, permission, credential), not one yes/no list, because the gate treats them differently: some can be opted in per routine (D11), some never can.
- We do include send, post and submit, since the product's rule is that outward-facing actions need a human click unless the worker opted that routine in. Gating is per routine and quiet, not per click.
- A label we cannot read does not default to safe: for model-driven steps the gate asks for the label from the DOM or accessibility tree first, and unknown targets in unattended runs go to the queue.
