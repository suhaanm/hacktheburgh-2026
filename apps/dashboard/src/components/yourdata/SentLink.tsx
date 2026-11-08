import { openSettings } from "../home/overlayStore";
import { Glyph } from "../needsyou/Glyph";

/**
 * What it looked at or sent, for a worker: one sentence, and one closed link to the list. The list itself (every call, exactly as sent) is under Settings,
 * Advanced, closed: that is the only place the call list appears for a worker (docs/knack-ux/views.md).
 */
export function SentLink() {
  return (
    <div className="yd-body" data-testid="sent">
      <p className="kc-row__body" style={{ margin: 0 }} data-testid="sent-line">Nothing leaves this Mac without your say.</p>
      <div>
        <button type="button" className="kc-link" onClick={() => openSettings("advanced")}>Every call Knack makes<Glyph name="chevron" /></button>
      </div>
    </div>
  );
}
