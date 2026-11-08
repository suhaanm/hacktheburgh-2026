// "About this screen": a side panel opened with Cmd-slash or the palette's "Explain this screen". What the screen is, where its numbers come from,
// and what it cannot tell you, in fixed words (about.ts). The facts a worker must see stay printed on the screen itself; this panel only explains.
import { useEffect, useRef } from "react";
import { screenOf, useRoute } from "../../router";
import { GROWTH_SECTION_LABEL, growthSectionOf, labelOf } from "../home/navModel";
import { closeAbout, useOverlay } from "../home/overlayStore";
import { aboutFor } from "./about";
import { Icon } from "./icons";
import { useStatus } from "./StatusLine";

export function AboutPanel() {
  const { about } = useOverlay();
  return about ? <Panel /> : null;
}

function Panel() {
  const route = useRoute();
  const current = screenOf(route);
  const status = useStatus();
  const box = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(typeof document === "undefined" ? null : document.activeElement);
  useEffect(() => {
    box.current?.querySelector<HTMLElement>("button")?.focus();
    const back = opener.current as HTMLElement | null;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); closeAbout(); } };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); if (back && document.contains(back)) back.focus(); };
  }, []);
  const section = current === "growth" ? growthSectionOf(route.query.get("section")) : null;
  const a = current === "unknown" ? null : aboutFor(current, section);
  const title = section && section !== "progress" ? GROWTH_SECTION_LABEL[section] : labelOf(current);
  return (
    <div className="drawer drawer--about" data-testid="about-panel">
      <div className="drawer__scrim drawer__scrim--clear" onClick={closeAbout} aria-hidden="true" />
      <div ref={box} className="drawer__panel" role="dialog" aria-modal="true" aria-labelledby="about-title">
        <header className="drawer__head">
          <h2 id="about-title" className="drawer__title">About {title}</h2>
          <button type="button" className="drawer__close" aria-label="Close" onClick={closeAbout}><Icon name="close" /></button>
        </header>
        <div className="drawer__body about">
          {a ? (
            <>
              <section><h3 className="about__h">What it is</h3><p>{a.what}</p></section>
              <section><h3 className="about__h">Where the numbers come from</h3><p>{a.from}</p></section>
              {a.limit && <section><h3 className="about__h">What it cannot tell you</h3><p>{a.limit}</p></section>}
            </>
          ) : <p>Open a screen from the menu and ask again.</p>}
          <section>
            <h3 className="about__h">Right now</h3>
            <p>{status.text}.</p>
          </section>
        </div>
      </div>
    </div>
  );
}
