# Your data and the memory file you own

> One place to see what Knack remembers, measures and has sent, with a delete beside each line. The memory file is the worker's, and only the worker's own actions can change it.

**Capability:** Privacy and safety · **Status:** built · **Master document:** `docs/PITCH_FEATURES.md` · **Index:** `docs/features/index.md`

This page covers Your data: see and delete, Memory file the worker owns.

## Your data: see and delete

**Status:** built (merged to main; owner has not used it) · **Page:** `docs/features/your-data.md` · **Targets:** G-Research

### What it does

Your data holds five things in one place: what Knack remembers, what it measures, what it looked at or sent, what your admin can see, and the capture and glance switches. Each line has a delete beside it, and 'Delete everything' asks for an exact confirmation.

### How it works

Seeing anything takes one click and deleting takes three at most (Your data, Forget, Forget it, confirmed inline). The delete wording is identical in every section. No file path is printed on screen. The worker's plain 'what your admin can see' page lives here. Capture, screen glances, the microphone and folders are controlled here; behaviour preferences live in Settings.

**What is different.** What Knack remembers, measures and has sent is one place with identical delete wording, instead of five scattered ones.

### Where to see it

Your data, the fifth item in the sidebar. The spec adds a palette row 'Delete my data' with no shortcut; it was not in the palette on main when this was written.

### Demo moment

Open Your data, press Forget beside one remembered line, confirm inline, and watch it leave. Then show What it looked at or sent with no pictures in it.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| Click budget: see in 1, delete in 3; five scattered places for 'my data' became one | design measurement of the old screens; replay script for the new paths | `docs/KNACK_UX.md (section 1, J5)` |

### Honest limit

Measured as a design, not by people. Deleting a worker's ledger removes them from admin comparisons at once (tested on synthetic firms), but nothing here shows how a real deployment would audit that.

### Hackathon target

- **G-Research (make the invisible visible)**: the worker can see what is held about them

## Memory file the worker owns

**Status:** built · **Page:** `docs/features/your-data.md` · **Targets:** G-Research

### What it does

Knack adapts to a worker through one readable, editable Markdown file on the device. Only the worker's own actions or approvals can write to it; page text, tool output and model text never do.

### How it works

Sections: Preferences, Procedure, Routines, Corrections, Skill state and Never, with a revision number in the header. Writes are atomic, a stale revision is rejected, the worker's edit wins and unknown sections are kept. A worker's correction is a precedent; three consistent ones become a proposed rule whose ceiling is no looser than anything already approved; a separate approval activates it; the rule is a versioned line, so deleting the line ends it. Precedents decay with a 30-day half-life. A personal procedure rule must also match expert outcomes in a shadow comparison. The first-run defaults come from the role pack.

**What is different.** Only the worker's own actions can write to it; a correction becomes a precedent, three consistent precedents become a proposal, and a separate approval activates it as a versioned line.

### Where to see it

Your data, 'What Knack remembers'; first run shows four plain lines from the file.

### Demo moment

Edit a line (for example a Never line) and show the next run respecting it; delete the line and show the rule ending.

### Evidence and its label

| What | Label | Source |
|---|---|---|
| An injection test checks that page text cannot write to memory or raise a rule's ceiling | offline tests | `docs/reference-notes/bandit.md; services/engine/tests/handoff/test_memory.py` |

### Honest limit

Mechanism tested offline; no worker has built a memory file by use. The precedent rule is an idea re-implemented from a hackathon project, with our own decay.

### Hackathon target

- **G-Research (make the invisible visible)**: the adaptation is a file the worker can read

## 30-second spoken script

> Your data is one place. What Knack remembers, what it measures, what it looked at or sent, and what your admin can see, each with a delete beside it. Seeing is one click and deleting is three. Behind it is a plain text file you own. Only your own actions can write to it; a web page or a model cannot. Delete a line and the rule it made is gone.

## Slide bullets

- One place for remembers, measures, looked-at-or-sent, admin-can-see, capture switches.
- See in 1 click, delete in 3; 'Delete everything' needs an exact confirmation.
- Memory is one readable file on the device.
- Only the worker's own actions or approvals can write; page and model text never do.
- Three consistent corrections become a proposed rule, activated by a separate approval.

## Sources

- `docs/KNACK_UX.md (sections 1, 3)`
- `docs/IMPLEMENTATION_SPEC.md (6.4, 7.1 memory)`
- `docs/reference-notes/bandit.md`
- `docs/DECISIONS.md (D41)`
- `docs/knack-ux/05-admin-firm.md`

## Related pages

`privacy-ledger.md`, `firm-admin.md`, `knack-shell.md`
