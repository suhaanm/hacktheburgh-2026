// Static markup of the Needs you rows (node environment, no browser): what must be printed, and which buttons carry which weight.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import queueFx from "../../fixtures/queue.json";
import routinesFx from "../../fixtures/routines.json";
import briefingFx from "../../fixtures/briefing.json";
import type { BriefingCard, QueueItem, Routine, TaskRow } from "../../types";
import { AwayButton, AwayConfirm, useAway } from "../routines/AwayChoice";
import { APPROVAL_TEXT, AWAY_TEXT, WATCH_TEXT } from "../routines/consent";
import { RunningRow } from "../routines/RunningRow";
import { ApprovalRow } from "./ApprovalRow";
import { PreparedRow } from "./PreparedRow";
import { ProposalDetails, ProposalRow } from "./ProposalRow";
import { TaskNeedRow } from "./TaskNeedRow";

const queue = (queueFx as unknown as { data: QueueItem[] }).data;
const routines = (routinesFx as unknown as { data: Routine[] }).data;
const cards = (briefingFx as unknown as { data: { cards: BriefingCard[] } }).data.cards;
const text = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, " ");
const noop = () => undefined;
const irreversible = queue.find((q) => q.risk_class === "irreversible")!;
const proposal = routines.find((r) => r.status === "proposed")!;

describe("an approval row", () => {
  const html = renderToStaticMarkup(createElement(ApprovalRow, { item: irreversible, primary: true, cls: 0, onDone: noop }));
  it("prints the consequence as plain text and keeps the irreversible-step label", () => {
    expect(text(html)).toContain("Cannot be undone.");
    expect(html).toMatch(/data-testid="consequence"/);
    expect(html).not.toMatch(/class="pill/);              // never a pill
    expect(text(html)).toContain("Approve and submit");
    expect(text(html)).toContain("Reject");
  });
  it("only the primary row has a primary button, and Reject is never primary", () => {
    expect(html).toMatch(/btn btn--primary[^>]*>Approve and submit/);
    expect(html).toMatch(/btn btn--secondary[^>]*>Reject/);
    const second = renderToStaticMarkup(createElement(ApprovalRow, { item: irreversible, primary: false, cls: 0, onDone: noop }));
    expect(second).not.toMatch(/btn--primary/);
  });
  it("has no keyboard shortcut and no key handler that could approve", () => {
    expect(html).not.toMatch(/accesskey|aria-keyshortcuts/i);
  });
  it("opens its evidence on demand, not by default", () => {
    expect(html).toMatch(/aria-expanded="false"/);
    expect(html).not.toMatch(/data-testid="evidence"/);
  });
});

describe("a routine proposal", () => {
  const html = renderToStaticMarkup(createElement(ProposalRow, { routine: proposal, onDecide: async () => undefined }));
  it("shows only Watch first and Not now, at one weight, none primary", () => {
    for (const label of ["Watch first", "Not now"]) expect(html).toMatch(new RegExp(`btn btn--secondary[^>]*>${label}<`));
    expect(html).not.toMatch(/btn--primary/);
    expect(html).not.toMatch(/>Never</);                       // behind Details, as light as the others
    expect(html).not.toMatch(/Run with my approval|Allow while/);
  });
  it("prints what it will never do, whole, as its own line, and never folds it", () => {
    const t = text(html);
    for (const n of proposal.proposal.never) expect(t.toLowerCase()).toContain(n.charAt(0).toLowerCase() + n.slice(1).replace(/\.$/, "").toLowerCase());
    expect(html).toMatch(/data-testid="never"[^>]*>(<p[^>]*>)?It will never/);
    if (proposal.proposal.never.length > 1) expect(html).toMatch(/<ul class="ny-never">/);       // several limits, one to a line
  });
  it("is one line of summary: what it would save as one range, and nothing about what it touches", () => {
    expect(text(html)).toMatch(/Could save [\d.]+ to [\d.]+ hours\./);
    expect(text(html)).not.toContain("Touches");
    expect(text(html)).not.toContain(WATCH_TEXT);
  });
  it("keeps the rest under Details, closed", () => {
    expect(html).toMatch(/aria-expanded="false"[^>]*>Details</);
    expect(html).not.toMatch(/data-testid="proposal-details"/);
  });
  it("opened, Details is one fact line, one short paragraph with every consent, and one row of actions", () => {
    const html2 = renderToStaticMarkup(createElement(ProposalDetails, { routine: proposal, touches: "a, b and c", busy: false, onApproval: noop, onNever: noop, onDecide: async () => undefined }));
    const open = text(html2);
    expect(open).toContain("Touches a, b and c");
    expect(open).toContain(WATCH_TEXT);
    expect(open).toContain(APPROVAL_TEXT);
    expect(open).toContain(AWAY_TEXT.slice(1));                     // the consent for running while away, whole, above its own button
    for (const label of ["Run with my approval", "Run while I'm away", "Never"]) expect(html2).toMatch(new RegExp(`btn btn--secondary btn--sm"[^>]*>${label.replace("'", "&#x27;")}<`));
    expect((html2.match(/kc-row__actions/g) ?? []).length).toBe(1);   // one row of actions
    expect((html2.match(/<p /g) ?? []).length).toBe(1);               // one paragraph
  });
});

describe("a prepared action", () => {
  const card = cards.find((c) => c.status === "ready")!;
  const html = renderToStaticMarkup(createElement(PreparedRow, { card, onFired: noop, onDismissed: noop, onChanged: noop }));
  it("has three choices of one weight and its details one click away", () => {
    for (const label of ["Approve and run", "Not now", "Never"]) expect(html).toMatch(new RegExp(`btn btn--secondary[^>]*>${label}<`));
    expect(text(html)).toContain("Details");
    expect(html).not.toMatch(/<textarea/);
  });
});

describe("Run while I'm away", () => {
  const irreversible = routines.find((x) => (x.irreversible_classes ?? []).length > 0)!;
  const plain = { ...routines[0], irreversible_classes: [] as string[], status: "approval" as const };
  const Button = (r: Routine) => function T() { const a = useAway(r, async () => undefined); return createElement(AwayButton, { away: a }); };
  const Confirm = (r: Routine) => function T() { const a = useAway(r, async () => undefined, undefined, true); return createElement(AwayConfirm, { away: a }); };
  it("is one button; a routine with steps that cannot be undone says it will ask (aria-expanded), one with none does not", () => {
    expect(renderToStaticMarkup(createElement(Button({ ...irreversible, status: "approval" })))).toMatch(/aria-expanded="false"[^>]*>Run while I&#x27;m away</);
    expect(renderToStaticMarkup(createElement(Button(plain)))).not.toMatch(/aria-expanded/);
  });
  it("asks once, in place: each step that cannot be undone is its own switch and starts off", () => {
    const html = renderToStaticMarkup(createElement(Confirm({ ...irreversible, status: "approval" })));
    expect(html).toMatch(/role="switch"/);
    expect(html).not.toMatch(/role="switch"[^>]*checked/);
    expect(text(html)).toContain("Allow while I'm away");
    expect(text(html)).toContain("each wait for your click unless you allow them");
    expect(html).toMatch(/Allow while I&#x27;m away<\/button>/);
    expect(html).not.toMatch(/disabled=""[^>]*>Allow while I&#x27;m away/);   // with nothing allowed, away runs may start: every step that cannot be undone still waits
    const allowed = renderToStaticMarkup(createElement(Confirm({ ...irreversible, status: "approval", consent: { ...irreversible.consent, irreversible_unattended: ["submit"] } })));
    expect(allowed).toMatch(/disabled=""[^>]*>Allow while I&#x27;m away/);     // with a step allowed, the second opt-in (typed id or acknowledgement) is needed first
  });
  it("when it is on it offers a way back and lists what was allowed", () => {
    const on = { ...irreversible, status: "unattended" as const, consent: { ...irreversible.consent, irreversible_unattended: ["submit"] } };
    const T = function T() { const a = useAway(on, async () => undefined, async () => undefined); return createElement("div", null, createElement(AwayButton, { away: a }), createElement(AwayConfirm, { away: a })); };
    const t = text(renderToStaticMarkup(createElement(T)));
    expect(t).toContain("Turn off away runs");
    expect(t).toContain("Allowed without asking: submit.");
  });
});

describe("a running routine", () => {
  const running = routines.find((r) => r.status === "approval")!;
  const closed = renderToStaticMarkup(createElement(RunningRow, { routine: running, open: false, onToggle: noop, onDecide: async () => undefined, onRun: async () => null, canRun: true }));
  const open = renderToStaticMarkup(createElement(RunningRow, { routine: running, open: true, onToggle: noop, onDecide: async () => undefined, onRun: async () => null, canRun: true }));
  it("closed, it is one title and one sentence, with Run now on the row, and the control that opens it has no words of its own", () => {
    expect(closed).toMatch(/<button[^>]*class="rt-row__open"[^>]*aria-label="[^"]+: open"[^>]*><\/button>/);
    expect(text(closed)).toContain("Run now");          // one click from the list
    expect(text(closed)).not.toMatch(/Stop for good/);
  });
  it("without the agent route there is no Run now", () => {
    expect(text(renderToStaticMarkup(createElement(RunningRow, { routine: running, open: false, onToggle: noop, onDecide: async () => undefined, canRun: false })))).not.toContain("Run now");
  });
  it("open, it is fact lines, one short paragraph and one row of actions: the steps, Run while I'm away and Stop for good, no Pause (the engine has none)", () => {
    expect(text(open)).toContain("Run now");
    expect(text(open)).toContain("Stop for good");
    expect(text(open)).toContain("Run while I'm away");
    expect(text(open)).not.toMatch(/\bPause\b/);
    expect(open).toMatch(/class="kc-kv"/);
    expect((open.match(/kc-row__actions/g) ?? []).length).toBe(1);
    expect(open).toMatch(/<summary>More<\/summary>/);                        // the record sits behind one closed More
    // Outside the closed "Record" disclosure (for reviewers) there is no rung code and no "rung".
    expect(text(open.replace(/<details[\s\S]*?<\/details>/g, ""))).not.toMatch(/\bA[0-3]\b|\brung\b/i);
  });
  it("the three steps are in the worker's words", () => {
    for (const w of ["Watch first", "Asks first", "Away runs"]) expect(text(open)).toContain(w);
  });
});

describe("a task that waits for the worker", () => {
  const consent: TaskRow = {
    task_id: "tk_8f3a1c2e", title: "Tidy the invoices folder", state: "waiting_consent", started: "2026-11-08T09:00:00Z",
    needs_consent: { kind: "folder", scope_text: "Knack wants to move files inside your Invoices folder.", can: ["read file names", "move files into Paid and Unpaid"], cannot: ["delete anything", "open other folders"], folder: "Invoices", max_minutes: 10, cost_note: "Uses live models.", buttons: { allow: "Allow", decline: "Decline", more: [{ id: "everything", label: "Allow everything this task needs" }] } },
  };
  const html = renderToStaticMarkup(createElement(TaskNeedRow, { row: consent, onDone: noop }));
  it("prints what the task may do and may not do, whole, before any button", () => {
    const t = text(html);
    expect(t).toContain("Knack wants to move files inside your Invoices folder.");
    expect(t).toContain("It can: read file names, move files into Paid and Unpaid.");
    expect(t).toContain("It cannot: delete anything, open other folders.");
    expect(t).toContain("Stops after 10 minutes.");
    expect(t.indexOf("It cannot")).toBeLessThan(t.indexOf("Decline"));
  });
  it("offers Allow and Decline at one weight, none primary, and keeps the wider choice behind More", () => {
    expect(html).toMatch(/btn btn--secondary[^>]*>Allow</);
    expect(html).toMatch(/btn btn--secondary[^>]*>Decline</);
    expect(html).not.toMatch(/btn--primary/);
    expect(html).toMatch(/<summary>More<\/summary>/);
    expect(html.indexOf("Allow everything this task needs")).toBeGreaterThan(html.indexOf("<summary>More</summary>"));
  });
  it("has no keyboard shortcut that could allow anything", () => {
    expect(html).not.toMatch(/accesskey|aria-keyshortcuts/i);
  });
  it("shows a question with its options as buttons, at most four", () => {
    const q: TaskRow = { task_id: "tk_2", title: "Rename the photos", state: "running", started: "2026-11-08T09:00:00Z", question: { text: "Which folder holds the photos?", options: [1, 2, 3, 4, 5, 6].map((n) => ({ id: `o${n}`, label: `Folder ${n}` })) } };
    const h = renderToStaticMarkup(createElement(TaskNeedRow, { row: q, onDone: noop }));
    expect(text(h)).toContain("Which folder holds the photos?");
    expect((h.match(/class="btn btn--secondary"/g) ?? []).length).toBe(4);
  });
  it("copes with a card that has no lists, no limits and a very long scope", () => {
    const h = renderToStaticMarkup(createElement(TaskNeedRow, { row: { task_id: "tk_3", title: "T".repeat(200), state: "waiting_consent", needs_consent: { scope_text: "S".repeat(900) } }, onDone: noop }));
    expect(h).not.toMatch(/data-testid="can"|data-testid="cannot"/);
    expect(text(h).length).toBeLessThan(900);
    expect(text(renderToStaticMarkup(createElement(TaskNeedRow, { row: { task_id: "tk_4", title: "A small task", state: "waiting_consent" } as TaskRow, onDone: noop })))).toContain("A small task");
  });
});
