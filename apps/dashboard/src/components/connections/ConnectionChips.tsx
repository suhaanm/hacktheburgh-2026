// "Connect your tools": the chips offered inside the first-run role card (CONNECTIONS). Every chip is OFF. A click shows the consent lines for the
// EXAMPLE connection (invented data on this Mac, no account); a second click, on "Connect", is what switches it on. Nothing connects without that click.
// A real connection (a token, a folder, a site address) is made in Settings, where the worker can type those.
import { useEffect, useId, useRef, useState } from "react";
import { connectBody, consentFor, isOn, stateTone, stateWord, type Connection } from "../../screens/Connections/model";
import { defaultClient, type ConnectionsClient } from "../../screens/Connections/client";
import "../kc.css";
import "./connections.css";

export interface ConnectionChipsProps {
  /** The role pack the worker chose (for example "programmer"). The chips are that pack's curated list. */
  role: string;
  /** Called with the ids that are on, after every change. */
  onChange?: (connected: string[]) => void;
  /** For tests: the client to use. */
  client?: ConnectionsClient;
}

export function ConnectionChips({ role, onChange, client }: ConnectionChipsProps) {
  const api = useRef<ConnectionsClient>(client ?? defaultClient());
  const [items, setItems] = useState<Connection[] | null>(null);
  const [example, setExample] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const head = useId();
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    let live = true;
    setItems(null);
    setOpen(null);
    api.current.list(role).then((r) => { if (live) { setItems(r.items); setExample(r.example); } }, () => { if (live) { setItems([]); setError("The list could not be read. Nothing was changed."); } });
    return () => { live = false; };
  }, [role]);

  const publish = (next: Connection[]) => { setItems(next); onChangeRef.current?.(next.filter(isOn).map((c) => c.id)); };
  const replace = (c: Connection) => (items ?? []).map((x) => (x.id === c.id ? c : x));

  const connect = async (c: Connection) => {
    setBusy(c.id); setError(null);
    try { publish(replace(await api.current.connect(c.id, connectBody(c, "example", {})))); setOpen(null); }
    catch (e) { setError(e instanceof Error ? e.message : "It could not be connected. Nothing was changed."); }
    finally { setBusy(null); }
  };
  const revoke = async (c: Connection) => {
    setBusy(c.id); setError(null);
    try { publish(replace(await api.current.revoke(c.id))); setOpen(null); }
    catch (e) { setError(e instanceof Error ? e.message : "It could not be revoked. Try again."); }
    finally { setBusy(null); }
  };

  if (items === null || items.length === 0) return error ? <p className="kc-error" role="alert">{error}</p> : null;
  const current = items.find((c) => c.id === open) ?? null;
  const consent = current ? consentFor(current, "example") : null;

  return (
    <section className="cx-chips" aria-labelledby={head}>
      <h2 className="cx-chips__h" id={head}>Connect your tools</h2>
      <ul className="cx-chiplist">
        {items.map((c) => (
          <li key={c.id}>
            <button type="button" className="cx-chip" aria-expanded={open === c.id} aria-controls={`cx-consent-${c.id}`} data-state={c.state}
                    onClick={() => setOpen(open === c.id ? null : c.id)}>
              <span className="cx-dot" data-tone={stateTone(c)} aria-hidden="true" />
              <span className="cx-chip__name">{c.app}</span>
              <span className="u-sr-only">, {stateWord(c)}</span>
              {isOn(c) && <span className="pill pill--origin" data-origin={c.example ? "example" : "real"}>{stateWord(c)}</span>}
              {c.caution && <span className="cx-chip__flag">{c.caution}</span>}
            </button>
          </li>
        ))}
      </ul>
      {current && consent && (
        <div className="cx-consent" id={`cx-consent-${current.id}`} role="region" aria-label={`${current.app} consent`}>
          <p className="cx-consent__title">{current.app}</p>
          <ul className="cx-lines">{consent.lines.map((l) => <li key={l}>{l}</li>)}</ul>
          <div className="cx-actions">
            {isOn(current)
              ? <button type="button" className="btn btn--secondary btn--sm" disabled={busy === current.id} onClick={() => void revoke(current)}>Revoke</button>
              : <button type="button" className="btn btn--primary btn--sm" disabled={busy === current.id} onClick={() => void connect(current)}>Connect</button>}
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setOpen(null)}>{isOn(current) ? "Close" : "Not now"}</button>
          </div>
        </div>
      )}
      {example && <p className="cx-note">Example connections: the engine is not running.</p>}
      {error && <p className="kc-error" role="alert">{error}</p>}
    </section>
  );
}

export default ConnectionChips;
