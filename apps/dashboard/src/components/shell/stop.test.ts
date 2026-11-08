// The Stop button draws ONE red square. The owner saw two: an icon in the markup and the design system's CSS square. These tests keep it to one, in the
// button, in the narrow top bar and in the in-window banner, and keep the stopped state printed in words (never only a colour).
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { StopFace, StoppedBar, sinceText } from "./StopControl";

const html = (el: ReturnType<typeof createElement>) => renderToStaticMarkup(el);
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const count = (hay: string, needle: string | RegExp) => (hay.match(typeof needle === "string" ? new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g") : needle) ?? []).length;

describe("the Stop button", () => {
  for (const killed of [false, true]) for (const compact of [false, true]) {
    it(`has the word and no square of its own (killed=${killed}, compact=${compact})`, () => {
      const out = html(createElement(StopFace, { killed, compact }));
      expect(count(out, "<span")).toBe(1);
      expect(count(out, "<svg")).toBe(0);
      expect(out).not.toMatch(/■|&#9632;|&#x25a0;|stop-icon|class="icon/i);
      expect(out).toContain(killed ? ">Resume<" : ">Stop<");
      expect(out).toContain(killed ? 'aria-label="Resume after stop"' : 'aria-label="Stop everything now"');
      expect(out).toContain(`aria-pressed="${killed}"`);
      expect(out.includes('data-compact="true"')).toBe(compact);
    });
  }
  it("takes its one square from the design system's CSS, and the shell adds none", () => {
    const design = read("../../../../../packages/design/components.css");
    const shell = read("../../styles/shell.css");
    expect(count(design, /\.stop-button::before\s*\{[^}]*content:\s*""/g)).toBe(1);
    expect(count(design, /\.stop-button::after/g)).toBe(0);
    expect(count(shell, /\.stop-button[^{]*::after/g)).toBe(0);
    // The shell may recolour the square in the stopped state, never draw one (no `content` on a stop-button pseudo element).
    for (const m of shell.match(/\.stop-button[^{]*::(?:before|after)\s*\{[^}]*\}/g) ?? []) expect(m, m).not.toMatch(/content\s*:/);
  });
  it("is drawn once per layout: once in the sidebar footer and once in the narrow top bar, no icon beside either", () => {
    const side = read("./Sidebar.tsx");
    expect(count(side, "<StopButton")).toBe(2);
    expect(side).toMatch(/<StopButton compact \/>/);
    expect(side).not.toMatch(/<Icon name="stop"|name="stop"/);
    expect(read("./icons.tsx")).not.toMatch(/\bstop:/);
  });
  it("has one stop control component, so a second one cannot be added without this test noticing", () => {
    const shellFiles = ["./Sidebar.tsx", "./AccountMenu.tsx", "./MoreSheet.tsx", "./StatusLine.tsx", "./SettingsSheet.tsx", "./AboutPanel.tsx"].map(read).join("\n");
    expect(count(shellFiles, 'className="stop-button"')).toBe(0);
    expect(count(read("./StopControl.tsx"), 'className="stop-button"')).toBe(1);
  });
});

describe("the in-window stopped banner", () => {
  it("says in words that everything is stopped, offers the way back, and carries one alert icon, not a stop square", () => {
    const out = html(createElement(StoppedBar, { killedAt: null }));
    expect(out).toContain("Everything is stopped.");
    expect(out).toContain("No agent will run and no routine will start.");
    expect(out).toContain(">Resume<");
    expect(count(out, "<svg")).toBe(1);
    expect(out).not.toContain("stop-button");
    expect(out).toContain('role="alert"');
  });
  it("prints when it began, and says nothing about a time it cannot read", () => {
    expect(sinceText(null)).toBe("");
    expect(sinceText("not a date")).toBe("");
    expect(sinceText("2026-11-08T14:05:00Z")).toMatch(/^ \(since \d{2}:\d{2}\)$/);
    expect(html(createElement(StoppedBar, { killedAt: "garbage" }))).not.toMatch(/Invalid Date|since/);
  });
  it("disables Resume while the request is out", () => {
    expect(html(createElement(StoppedBar, { killedAt: null, busy: true }))).toMatch(/<button[^>]*disabled[^>]*>Resume</);
  });
});
