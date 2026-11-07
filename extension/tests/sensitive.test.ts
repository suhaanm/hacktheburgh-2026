import { beforeEach, describe, expect, it } from "vitest";
import { matcher, setPage } from "./helpers";
import { SensitiveMatcher } from "../src/shared/sensitive";

const q = (sel: string) => document.querySelector(sel)!;

describe("SensitiveMatcher", () => {
  beforeEach(() => setPage(""));

  it.each([
    '<input type="password" name="x">',
    '<input name="user_password">',
    '<input id="ni_number">',
    '<input placeholder="National Insurance number">',
    '<input aria-label="Card number">',
    '<input autocomplete="cc-number">',
    '<input autocomplete="one-time-code">',
    '<input name="otp">',
    '<input name="sort code">',
    '<label for="a">Date of birth</label><input id="a">',
    '<label>Security code <input name="q1"></label>',
    '<span id="l">Account number</span><input aria-labelledby="l">',
    '<input type="email" name="contact">',
    '<input name="home address">',
    '<textarea name="medical notes"></textarea>',
    '<input name="national_insurance_number">',
    '<input name="nationalInsurance">',
    '<input id="card.number">',
    '<input name="date_of_birth">',
    '<input name="sort-code">',
  ])("flags %s", (html) => {
    setPage(html);
    expect(matcher.isSensitiveElement(q("input, textarea"))).toBe(true);
  });

  it.each([
    '<input name="adults">', '<input name="your_age" type="number">', '<input id="result-a">',
    '<input name="savings">', '<select name="tenure"></select>', '<button id="continue">Continue</button>',
    '<input name="rent">', '<textarea id="note-text"></textarea>', '<input type="search" name="q">',
  ])("does not flag %s", (html) => {
    setPage(html);
    expect(matcher.isSensitiveElement(q("input, select, button, textarea"))).toBe(false);
  });

  it("treats every field of a login form as sensitive", () => {
    setPage('<form><input name="username"><input type="password" name="p"><button id="go">Go</button></form>');
    expect(matcher.inSensitiveContext(q("[name=username]"))).toBe(true);
    expect(matcher.inSensitiveContext(q("#go"))).toBe(true);
  });

  it("does not drop an ordinary form because one control is an email field elsewhere", () => {
    setPage('<form id="f"><input name="adults"><button id="go">Go</button></form>');
    expect(matcher.inSensitiveContext(q("#go"))).toBe(false);
  });

  it("looks a few levels up for login containers without a form", () => {
    setPage('<div><div><input name="u" id="u"><input type="password" id="p"></div></div>');
    expect(matcher.inSensitiveContext(q("#u"))).toBe(true);
  });

  it("fails closed when a pattern does not compile", () => {
    const m = new SensitiveMatcher([{ patterns: ["(unclosed"] }]);
    expect(m.isSensitiveText("a (unclosed paren")).toBe(true);
  });

  it("merges autocomplete tokens and input types from every list", () => {
    const m = new SensitiveMatcher([{ patterns: ["zzz"], autocomplete_tokens: ["tel"], input_types: ["tel"] }]);
    setPage('<input type="tel" name="n">');
    expect(m.isSensitiveElement(q("input"))).toBe(true);
  });
});
