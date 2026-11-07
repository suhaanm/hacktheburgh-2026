import type { WireSharing } from "../firm/wire";
import { previewLines } from "../firm/model";
import { Details } from "../ui";

const KIND: Record<string, string> = { number: "numbers", enum: "a plain class", count: "counts" };

/**
 * What your admin can see: a read-only list. It is not a setting, so there is no switch: it says plainly what an admin sees about you, what they never
 * see, and exactly the row they get. For coaching and onboarding, not for evaluating individuals.
 */
export function AdminSees({ sharing }: { sharing: WireSharing }) {
  const lines = previewLines(sharing.preview);
  return (
    <div className="yd-body" data-testid="admin-sees">
      {sharing.notice && <p className="kc-row__body" style={{ margin: 0 }}>{sharing.notice}</p>}
      <div>
        <p className="kc-label">They can see</p>
        <ul className="yd-plain">{sharing.items.map((i) => <li key={i.id}>{i.label} <span className="u-muted">({KIND[i.kind] ?? i.kind})</span></li>)}</ul>
      </div>
      <div>
        <p className="kc-label">They can never see</p>
        <ul className="yd-plain">{sharing.never.map((n) => <li key={n}>{n}</li>)}</ul>
      </div>
      {lines.length > 0 && (
        <Details summary="Show exactly what they see about you" wide>
          <dl className="about__list">
            {lines.map(([k, v]) => (<div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>))}
          </dl>
        </Details>
      )}
      {(sharing.visible_to || sharing.visible_since) && <p className="kc-sub">{sharing.visible_to ?? ""}{sharing.visible_since ? ` Visible since ${sharing.visible_since}.` : ""}</p>}
      {sharing.legal_note && <p className="kc-sub">{sharing.legal_note}</p>}
    </div>
  );
}
