import { beforeEach, describe, expect, it } from "vitest";
import { accessibleName, interactiveAncestor, isFormField, roleOf } from "../src/shared/dom";
import { pickSite, Zoner } from "../src/shared/zones";
import { setPage, zoneConfig, zonerFor } from "./helpers";

const q = (sel: string) => document.querySelector(sel)!;

describe("dom helpers", () => {
  beforeEach(() => setPage(""));
  it("derives ARIA roles", () => {
    setPage('<a href="#" id="a">x</a><button id="b">y</button><input id="c" type="number"><input id="d" type="search"><select id="e"></select><div id="f" role="tab"></div><textarea id="g"></textarea><input id="h" type="checkbox">');
    expect(["a", "b", "c", "d", "e", "f", "g", "h"].map((i) => roleOf(q("#" + i)))).toEqual(["link", "button", "spinbutton", "searchbox", "combobox", "tab", "textbox", "checkbox"]);
  });
  it("computes accessible names from label, aria-label, text and value", () => {
    setPage('<label for="i">Your age</label><input id="i"><button id="b" aria-label="Close">x</button><button id="t"> Check  cliff   edges </button><input id="s" type="submit" value="Save draft">');
    expect(accessibleName(q("#i"))).toBe("Your age");
    expect(accessibleName(q("#b"))).toBe("Close");
    expect(accessibleName(q("#t"))).toBe("Check cliff edges");
    expect(accessibleName(q("#s"))).toBe("Save draft");
  });
  it("finds the interactive ancestor of a nested node", () => {
    setPage('<button id="b"><span id="s"><b id="x">go</b></span></button>');
    expect(interactiveAncestor(q("#x"))).toBe(q("#b"));
  });
  it("recognises form fields", () => {
    setPage('<input id="a"><input id="b" type="submit"><div id="c"></div><div id="d" role="textbox"></div>');
    expect([isFormField(q("#a")), isFormField(q("#b")), isFormField(q("#c")), isFormField(q("#d"))]).toEqual([true, false, false, true]);
  });
});

describe("zones", () => {
  beforeEach(() => setPage(""));
  it("picks the site by host, with wildcards and the role's packs", () => {
    expect(pickSite(zoneConfig, "127.0.0.1:7801")?.id).toBe("a");
    expect(pickSite(zoneConfig, "localhost:7802")?.id).toBe("b");
    expect(pickSite(zoneConfig, "acme.snowflakecomputing.com")?.pack).toBe("data-analyst");
    expect(pickSite(zoneConfig, "acme.snowflakecomputing.com", ["benefits-processor"])).toBeNull();
    expect(pickSite(zoneConfig, "example.org")).toBeNull();
    expect(pickSite(zoneConfig, "snowflakecomputing.com")).toBeNull(); // a bare domain is not a *.sub match
  });

  it("derives sandbox zones from selectors, cliff elements winning over the page", () => {
    setPage('<form action="/step/2?x=1"><input id="f" name="adults"><button id="continue">go</button></form>' +
      '<p id="result-amount">£1</p><button id="cliff-btn">Check cliff edges</button><div id="cliff-panel" role="region"><li data-cliff="capital_limit">t</li></div>');
    const z = zonerFor("127.0.0.1:7801");
    expect(z.forElement(q("#f"), "textbox")).toBe("household_form");
    expect(z.forElement(q("#continue"), "button")).toBe("household_form");
    expect(z.forElement(q("#result-amount"), "generic")).toBe("calc_result");
    expect(z.forElement(q("#cliff-btn"), "button")).toBe("cliff_button");
    expect(z.forElement(q("[data-cliff]"), "listitem")).toBe("cliff_panel");
  });

  it("derives nav, scroll and tab zones from the document's markers", () => {
    const z = zonerFor("127.0.0.1:7801");
    setPage('<form action="/step/1"><input name="adults"></form>');
    expect(z.forNav(document)).toBe("calc_site");
    expect(z.forScroll(document)).toBe("household_form");
    expect(z.forTab(document)).toBe("results_tabs");
    setPage('<form action="/step/2"><input type="hidden" name="a" value="1"></form>');
    expect(z.forNav(document)).toBe("household_form");
    setPage('<strong id="result-amount">£1</strong>');
    expect(z.forNav(document)).toBe("calc_result");
    expect(z.forScroll(document)).toBe("calc_result");
    setPage('<form action="/casenote/draft"><input name="case_ref"></form>');
    expect(z.forNav(document)).toBe("case_note");
    expect(z.forTab(document)).toBe("case_note");
    expect(z.forScroll(document)).toBe("case_note");
  });

  it("honours data-understudy-zone only for vocabulary values", () => {
    setPage('<div data-understudy-zone="cliff_panel"><span id="a">x</span></div><div data-understudy-zone="https://evil.example"><span id="b">x</span></div>');
    const z = zonerFor("example.org");
    expect(z.forElement(q("#a"), "generic")).toBe("cliff_panel");
    expect(z.forElement(q("#b"), "generic")).toBeUndefined();
  });

  it("falls back to generic base zones from the ARIA role when no site matches", () => {
    setPage('<input id="t"><input id="s" type="search">');
    const z = zonerFor("example.org");
    expect(z.forElement(q("#t"), "textbox")).toBe("form_field");
    expect(z.forElement(q("#s"), "searchbox")).toBe("search_box");
    expect(z.forScroll(document)).toBe("doc");
    expect(z.forNav(document)).toBeUndefined();
  });

  it("survives a bad selector in a pack", () => {
    const cfg = { vocabulary: ["x"], sites: [{ pack: "p", id: "s", hosts: ["h"], nav_default: "x", tab_default: "x", elements: [{ zone: "x", selector: "[[[" }] }] };
    setPage('<i id="a"></i>');
    const z = new Zoner(cfg, cfg.sites[0]!);
    expect(z.forElement(q("#a"), "generic")).toBeUndefined();
  });
});
