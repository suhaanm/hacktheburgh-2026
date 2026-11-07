import { previewLines } from "../firm/model";
import type { WireSharing } from "../firm/wire";
import { Details } from "../ui";

const KIND: Record<string, string> = { number: "numbers", enum: "a plain class", count: "counts" };

/** "What your admin can see": a read-only list. No switch, because this is not a setting: it says plainly what an admin sees and what they never do. */
export function SharingPanel({ sharing }: { sharing: WireSharing }) {
  const lines = previewLines(sharing.preview);
  return (
    <div className="home__share">
      {sharing.notice && <p>{sharing.notice}</p>}
      <h4 className="t-label">They can see</h4>
      <ul className="home__list">
        {sharing.items.map((i) => <li key={i.id}>{i.label} <span className="home__kind">({KIND[i.kind] ?? i.kind})</span></li>)}
      </ul>
      <h4 className="t-label">They can never see</h4>
      <ul className="home__list">
        {sharing.never.map((n) => <li key={n}>{n}</li>)}
      </ul>
      {lines.length > 0 && (
        <Details summary="Show exactly what they see about you" wide>
          <dl className="about__list">
            {lines.map(([k, v]) => (<div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>))}
          </dl>
        </Details>
      )}
      {(sharing.visible_to || sharing.visible_since) && (
        <p className="home__source">
          {sharing.visible_to ?? ""}{sharing.visible_since ? ` Visible since ${sharing.visible_since}.` : ""}
        </p>
      )}
      {sharing.legal_note && <p className="home__source">{sharing.legal_note}</p>}
    </div>
  );
}
