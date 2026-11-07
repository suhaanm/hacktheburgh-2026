// The Knack row, confirm row and icon set: structure, accessibility and the rules of KNACK_UX section 6. Static markup, no DOM needed.
// The behaviour of ConfirmRow (focus on Keep, Escape means Keep) is checked in a real DOM in ConfirmRow.dom.test.ts.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ICONS, ICON_NAMES, SPEC_ICONS, Icon } from "./Icon";
import { ConfirmRow, Row, Rows } from "./ui";

const html = (el: ReturnType<typeof createElement>) => renderToStaticMarkup(el);

describe("Icon", () => {
  it("has the fourteen icons of the spec", () => {
    expect(SPEC_ICONS).toHaveLength(14);
    for (const n of SPEC_ICONS) expect(ICON_NAMES).toContain(n);
  });

  it("is a 16 px grid, currentColor, decorative unless named", () => {
    const out = html(createElement(Icon, { name: "home" }));
    expect(out).toContain('viewBox="0 0 16 16"');
    expect(out).toContain('aria-hidden="true"');
    expect(out).not.toContain("#");
    expect(html(createElement(Icon, { name: "alert", label: "Warning" }))).toContain('aria-label="Warning"');
  });

  it("every icon draws something and uses no hard-coded colour", () => {
    for (const n of ICON_NAMES) {
      const out = html(createElement(Icon, { name: n }));
      expect(out, n).toMatch(/<(path|circle|rect)/);
      expect(out, n).not.toMatch(/fill="#|stroke="#|rgb\(/);
    }
    expect(Object.keys(ICONS)).toEqual(ICON_NAMES);
  });
});

describe("Row", () => {
  it("a link row is the whole target with a chevron", () => {
    const out = html(createElement(Rows, null, createElement(Row, { title: "Juniors take longer", meta: "n = 29 people", href: "#/roles", icon: "alert" })));
    expect(out).toContain('<ul class="listrows"');
    expect(out).toMatch(/<li><a class="listrow" href="#\/roles">/);
    expect(out).toContain("listrow__chev");
    expect(out).toContain("n = 29 people");
  });

  it("a button row is a button, never a div with a click handler", () => {
    const out = html(createElement(Rows, null, createElement(Row, { title: "Open", onClick: () => undefined })));
    expect(out).toContain('<button type="button" class="listrow"');
  });

  it("a plain row can carry actions, which show on hover and focus", () => {
    const out = html(createElement(Rows, null, createElement(Row, { title: "A memory line", actions: createElement("button", { type: "button" }, "Forget") })));
    expect(out).toContain('<div class="listrow"');
    expect(out).toContain("listrow__actions");
    expect(out).not.toContain("listrow__chev");
  });

  it("a link row never renders actions (a link cannot hold buttons)", () => {
    const out = html(createElement(Rows, null, createElement(Row, { title: "x", href: "#/x", actions: createElement("button", { type: "button" }, "Forget") })));
    expect(out).not.toContain("<button");
  });

  it("tone only colours the icon; the words stay", () => {
    const out = html(createElement(Rows, null, createElement(Row, { title: "An approval has waited 72 hours", icon: "alert", tone: "warn" })));
    expect(out).toContain("listrow__icon--warn");
    expect(out).toContain("An approval has waited 72 hours");
  });
});

describe("ConfirmRow", () => {
  it("prints the question and the consequence, and offers Keep and the confirm word", () => {
    const out = html(createElement(Rows, null, createElement(ConfirmRow, { question: "Forget this line?", consequence: "It cannot be undone.", confirmLabel: "Forget it", onConfirm: () => undefined, onCancel: () => undefined })));
    expect(out).toContain('role="group"');
    expect(out).toContain("Forget this line?");
    expect(out).toContain("It cannot be undone.");
    expect(out).toContain(">Keep<");
    expect(out).toContain(">Forget it<");
  });
});
