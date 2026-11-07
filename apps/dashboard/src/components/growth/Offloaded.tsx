import { plural, type OffloadItem } from "./model";

/** Work done for the person. Counted and listed apart from the score, and said to be outside it. */
export function Offloaded({ delegated, automation, items }: { delegated: number; automation: number; items: OffloadItem[] }) {
  const none = delegated + automation === 0;
  return (
    <section className="section gr-off" aria-labelledby="off-h">
      <div className="section__head">
        <h2 id="off-h" className="section__title">Work done for you</h2>
      </div>
      <p className="section__sub">Runs you asked the agent to do, and automations that ran in the background or overnight. These never change your independence score, so handing work off cannot raise it or lower it.</p>
      {none ? (
        <p className="note">Nothing has run for you yet.</p>
      ) : (
        <>
          <p className="gr-off__counts num">
            <span><b>{delegated}</b> {delegated === 1 ? "run you asked for" : "runs you asked for"}</span>
            <span><b>{automation}</b> {automation === 1 ? "overnight automation" : "overnight automations"}</span>
          </p>
          {items.length > 0 && (
            <ol className="gr-off__list">
              {items.map((i) => (
                <li key={i.id} className="gr-off__item">
                  <span className="gr-off__when num">{i.when}</span>
                  <span className="gr-off__what">{i.streamWord}: {i.skill}</span>
                  <span className="gr-off__outcome">{i.outcome}</span>
                </li>
              ))}
            </ol>
          )}
          {items.length > 0 && items.length < delegated + automation && <p className="note">Showing the latest {plural(items.length, "run")}.</p>}
        </>
      )}
    </section>
  );
}
