import type { WireSharing } from "../firm/wire";
import { previewLines } from "../firm/model";
import { Details } from "../ui";

const KIND: Record<string, string> = { number: "numbers", enum: "a plain class", count: "counts" };
const arr = <T,>(x: T[] | null | undefined): T[] => (Array.isArray(x) ? x : []);

/**
 * What your admin can see: read-only, so there is no switch. ONE short paragraph (the engine's own notice: what an admin sees about you, and that it is for
 * coaching and onboarding, not for evaluating individuals) and, under one closed "More", exactly what they can and can never see, the row they get, and
 * since when. Every list may be missing.
 */
export function AdminSees({ sharing }: { sharing: WireSharing }) {
  const lines = previewLines(sharing.preview ?? null);
  const items = arr(sharing.items), never = arr(sharing.never);
  const notice = sharing.notice ?? "Your admin sees a summary of numbers about your work. It is for coaching and onboarding, not for evaluating individuals.";
  return (
    <div className="yd-body" data-testid="admin-sees">
      <p className="kc-row__body" style={{ margin: 0 }}>{notice}</p>
      <Details summary="More" wide>
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {items.length > 0 && <div><p className="kc-label">They can see</p><ul className="yd-plain">{items.map((i) => <li key={i.id}>{i.label} <span className="u-muted">({KIND[i.kind] ?? i.kind})</span></li>)}</ul></div>}
          {never.length > 0 && <div><p className="kc-label">They can never see</p><ul className="yd-plain">{never.map((n) => <li key={n}>{n}</li>)}</ul></div>}
          {lines.length > 0 && (
            <div><p className="kc-label">Exactly what they see about you</p>
              <dl className="about__list">{lines.map(([k, v]) => (<div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>))}</dl></div>
          )}
          {(sharing.visible_to || sharing.visible_since) && <p className="kc-sub">{sharing.visible_to ?? ""}{sharing.visible_since ? ` Visible since ${sharing.visible_since}.` : ""}</p>}
          {sharing.legal_note && <p className="kc-sub">{sharing.legal_note}</p>}
        </div>
      </Details>
    </div>
  );
}
