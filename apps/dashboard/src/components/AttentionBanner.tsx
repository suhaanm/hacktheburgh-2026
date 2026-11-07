import { useEffect, useState } from "react";
import { api } from "../api";
import { useAppState } from "../store";
import { bannerReading } from "../lib/attention";
import type { AttentionPeek } from "../types";

const EVERY_MS = 15_000;

/**
 * A passive line at the top of the page: how many notices are waiting, and a link to the summary when one is ready. It reads counts
 * only and delivers nothing; the desktop decides what is drawn on screen. The stopped state is the Stop pill's, never this line's.
 * It shows nothing at all unless the engine really answered (never from example data) and the layer is on.
 */
export function AttentionBanner() {
  const app = useAppState();
  const [peek, setPeek] = useState<AttentionPeek | null>(null);
  const on = app.extReady && app.ext.attention === true;

  useEffect(() => {
    if (!on) { setPeek(null); return; }
    let live = true;
    const look = () => {
      if (document.visibilityState === "hidden") return;
      api.attentionPeek(app.person ?? undefined).then((r) => { if (live) setPeek(r.source === "live" ? r.data : null); }, () => { if (live) setPeek(null); });
    };
    look();
    const id = window.setInterval(look, EVERY_MS);
    return () => { live = false; window.clearInterval(id); };
  }, [on, app.person]);

  const b = bannerReading(peek?.badges, peek?.digest_ready === true);
  if (!b.show) return null;
  return (
    <div className="noticebar" role="status" data-testid="notice-banner">
      {b.text && <span>{b.text}.</span>}
      {b.summary && <a href="#/notices">Summary ready</a>}
      {b.text && !b.summary && <a href="#/notices">See notices</a>}
    </div>
  );
}
