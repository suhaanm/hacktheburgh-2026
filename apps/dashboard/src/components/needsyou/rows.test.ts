// Static markup of the Needs you rows (node environment, no browser): what must be printed, and which buttons carry which weight.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import queueFx from "../../fixtures/queue.json";
import routinesFx from "../../fixtures/routines.json";
import briefingFx from "../../fixtures/briefing.json";
import type { BriefingCard, QueueItem, Routine } from "../../types";
import { AwayChoice } from "../routines/AwayChoice";
import { AWAY_TEXT, WATCH_TEXT } from "../routines/consent";
import { RunningRow } from "../routines/RunningRow";
import { ApprovalRow } from "./ApprovalRow";
import { PreparedRow } from "./PreparedRow";
import { MoreWays, ProposalRow } from "./ProposalRow";

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
  it("offers Watch first, Not now and Never at one weight, none primary", () => {
    for (const label of ["Watch first", "Not now", "Never"]) expect(html).toMatch(new RegExp(`btn btn--secondary[^>]*>${label}<`));
    expect(html).not.toMatch(/btn--primary/);
  });
  it("prints what it will never do, whole, as its own line", () => {
    const t = text(html);
    for (const n of proposal.proposal.never) expect(t.toLowerCase()).toContain(n.charAt(0).toLowerCase() + n.slice(1).replace(/\.$/, "").toLowerCase());
    expect(t).toContain("It will never");
    expect(html).toMatch(/data-testid="never"[^>]*>(<p[^>]*>)?It will never/);
    if (proposal.proposal.never.length > 1) expect(html).toMatch(/<ul class="ny-never">/);       // several limits, one to a line
  });
  it("keeps the other ways to say yes one click away, under a short visible label with the whole name for a screen reader", () => {
    expect(html).toMatch(/aria-label="More ways to say yes"[^>]*aria-expanded="false"[^>]*>More ways</);
    expect(text(html)).not.toContain(WATCH_TEXT);
    expect(html).not.toMatch(/data-testid="more-ways"/);
  });
  it("opened, it prints what every way of saying yes does, with the away consent next to its own button", () => {
    const open = text(renderToStaticMarkup(createElement(MoreWays, { routine: proposal, busy: false, onApproval: noop, onDecide: async () => undefined })));
    expect(open).toContain(WATCH_TEXT);
    expect(open).toContain("Run with my approval");
    expect(open).toContain(AWAY_TEXT);
    expect(open).toContain("Allow while I'm away");
  });
  it("says the interval behind the hours is in the hint, and prints one range", () => {
    expect(text(html)).toMatch(/Could save [\d.]+ to [\d.]+ hours\./);
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
  it("prints its consent whole next to its one button, and the irreversible opt-in as separate switches that start off", () => {
    const r = routines.find((x) => (x.irreversible_classes ?? []).length > 0)!;
    const html = renderToStaticMarkup(createElement(AwayChoice, { routine: { ...r, status: "approval" }, onDecide: async () => undefined }));
    expect(text(html)).toContain(AWAY_TEXT);
    expect(text(html)).toContain("Allow while I'm away");
    expect(html).toMatch(/role="switch"/);
    expect(html).not.toMatch(/role="switch"[^>]*checked/);
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
  it("open, it offers Stop for good but no Pause (the engine has none), and Run now stays on the row", () => {
    expect(text(open)).toContain("Run now");
    expect(text(open)).toContain("Stop for good");
    expect(text(open)).not.toMatch(/\bPause\b/);
    expect(text(open)).toContain("Autonomy");
    // Outside the closed "Record" disclosure (for reviewers) there is no rung code and no "rung".
    expect(text(open.replace(/<details[\s\S]*?<\/details>/g, ""))).not.toMatch(/\bA[0-3]\b|\brung\b/i);
  });
  it("the three steps are in the worker's words", () => {
    for (const w of ["Watching", "Asks first", "Runs on its own"]) expect(text(open)).toContain(w);
  });
});
