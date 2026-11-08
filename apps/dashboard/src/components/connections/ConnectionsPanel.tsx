// The Connections section of Settings (CONNECTIONS): the curated apps the worker can connect, each OFF until clicked, with a status, a Connect or Revoke
// button, and what it has read as counts only. A real connection asks for the folder or address and the token it needs and shows the consent lines (who
// publishes it, which package and version, which hosts, "with your token") before the click that connects. Revoke is one click and a confirm; it forgets the
// token and stops the process. The token is typed into a password field, goes in one request, and is cleared at once: it is never shown, stored or kept.
import { Fragment, useEffect, useRef, useState } from "react";
import { ConfirmRow, Details } from "../ui";
import {
  GROUP_LABEL, TRAFFIC_NOTE, byGroup, connectBody, consentFor, fieldsFor, hasReal, isOn, metaLine, onFirst, problemWith, stateTone, stateWord,
  type Connection, type ConnMode,
} from "../../screens/Connections/model";
import { defaultClient, type ConnectionsClient } from "../../screens/Connections/client";
import "../kc.css";
import "./connections.css";

export interface ConnectionsPanelProps {
  /** For tests: the client to use. */
  client?: ConnectionsClient;
}

function ConnectForm({ c, busy, onConnect, onCancel }: { c: Connection; busy: boolean; onConnect: (mode: ConnMode, values: Record<string, string>) => void; onCancel: () => void }) {
  const [mode, setMode] = useState<ConnMode>("example");
  const [values, setValues] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const fields = fieldsFor(c, mode);
  const consent = consentFor(c, mode);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => { first.current?.focus(); }, [mode]);
  if (!consent) return null;
  const submit = () => {
    const p = problemWith(c, mode, values);
    if (p) { setProblem(p); return; }
    onConnect(mode, values);
    setValues({});                                   // the token leaves this component's state the moment it is handed over
  };
  return (
    <form className="cx-form" onSubmit={(e) => { e.preventDefault(); submit(); }} aria-label={`Connect ${c.app}`}>
      {hasReal(c) && (
        <div className="segmented" role="group" aria-label="Which kind of connection">
          <button type="button" aria-pressed={mode === "example"} onClick={() => { setMode("example"); setProblem(null); }}>Sandbox</button>
          <button type="button" aria-pressed={mode === "real"} onClick={() => { setMode("real"); setProblem(null); }}>Real</button>
        </div>
      )}
      {fields.map((f, i) => (
        <div className="cx-field" key={`${mode}-${f.key}`}>
          <label htmlFor={`cx-${c.id}-${f.key}`}>{f.label}</label>
          <input id={`cx-${c.id}-${f.key}`} ref={i === 0 ? first : undefined} type={f.secret ? "password" : "text"} value={values[f.key] ?? ""} autoComplete="off" spellCheck={false}
                 autoCapitalize="off" data-secret={f.secret ? "true" : undefined} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} />
        </div>
      ))}
      <ul className="cx-lines" aria-label="What you agree to">{consent.lines.map((l) => <li key={l}>{l}</li>)}</ul>
      {mode === "real" && c.modes.real && (
        <Details summary="About this server">
          <dl className="cx-facts">
            <dt>Publisher</dt><dd>{consent.publisher}</dd>
            <dt>Package</dt><dd>{consent.package} {consent.version}</dd>
            <dt>Licence</dt><dd>{consent.license ?? ""}</dd>
            <dt>Talks to</dt><dd>{consent.hosts.length ? consent.hosts.join(", ") : "Nothing outside this Mac"}</dd>
          </dl>
        </Details>
      )}
      {problem && <p className="kc-error" role="alert">{problem}</p>}
      <div className="cx-actions">
        <button type="submit" className="btn btn--primary btn--sm" disabled={busy}>Connect</button>
        <button type="button" className="btn btn--quiet btn--sm" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

export function ConnectionsPanel({ client }: ConnectionsPanelProps) {
  const api = useRef<ConnectionsClient>(client ?? defaultClient());
  const [items, setItems] = useState<Connection[] | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ id: string; message: string } | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.current.list().then((r) => { if (live) { setItems(r.items); } }, () => { if (live) setItems([]); });
    return () => { live = false; };
  }, []);

  const swap = (c: Connection) => setItems((cur) => (cur ?? []).map((x) => (x.id === c.id ? c : x)));
  const run = async (c: Connection, task: () => Promise<Connection>, done?: (r: Connection) => void) => {
    setBusy(c.id); setError(null); setSaved(null);
    try { const r = await task(); swap(r); done?.(r); }
    catch (e) { setError({ id: c.id, message: e instanceof Error ? e.message : "That did not work. Nothing was changed." }); }
    finally { setBusy(null); }
  };

  if (items === null) return <p className="cx-note" aria-live="polite">Reading your connections.</p>;
  const ordered = onFirst(items);
  return (
    <div className="cx-panel">
      {byGroup(ordered).map(({ group, items: rows }) => (
        <Details key={group} className="cx-group" defaultOpen={rows.some(isOn)} summary={`${GROUP_LABEL[group]} (${rows.length})`}>
          <ul className="cx-list" aria-label={GROUP_LABEL[group]}>
            {rows.map((c) => (
              <Fragment key={c.id}>
                <li className="cx-row" id={`conn-${c.id}`}>
                  <div className="cx-row__top">
                    <div className="cx-row__main">
                      <span className="cx-row__title">
                        {isOn(c) && <span className="cx-dot" data-tone={stateTone(c)} aria-hidden="true" />}
                        {c.app}
                        {isOn(c) && <span className="pill">{stateWord(c)}</span>}
                      </span>
                      <span className="cx-row__meta">{metaLine(c)}{c.caution && <> <span className="cx-flag">{c.caution}</span></>}</span>
                    </div>
                    <div className="cx-actions">
                      {c.state === "off" && <button type="button" className="btn btn--secondary btn--sm" aria-label={`Connect ${c.app}`} onClick={() => { setOpening(opening === c.id ? null : c.id); setRevoking(null); }}>Connect</button>}
                      {c.state === "needs_reconfirm" && <button type="button" className="btn btn--primary btn--sm" disabled={busy === c.id} onClick={() => void run(c, () => api.current.reconfirm(c.id))}>Confirm again</button>}
                      {isOn(c) && <button type="button" className="btn btn--quiet btn--sm" aria-label={`Revoke ${c.app}`} onClick={() => { setRevoking(revoking === c.id ? null : c.id); setOpening(null); }}>Revoke</button>}
                    </div>
                  </div>
                  {opening === c.id && c.state === "off" && (
                    <ConnectForm c={c} busy={busy === c.id} onCancel={() => setOpening(null)}
                      onConnect={(mode, values) => void run(c, () => api.current.connect(c.id, connectBody(c, mode, values)), (r) => { setOpening(null); if (r.agent === "offline") setSaved(c.id); })} />
                  )}
                  {saved === c.id && <p className="cx-note" role="status">Saved. It starts when the agent service runs.</p>}
                  {error?.id === c.id && <p className="kc-error" role="alert">{error.message}</p>}
                </li>
                {revoking === c.id && (
                  <ConfirmRow question={`Revoke ${c.app}?`} consequence="Its token is forgotten and it stops." confirmLabel="Revoke" busy={busy === c.id}
                              onCancel={() => setRevoking(null)} onConfirm={() => void run(c, () => api.current.revoke(c.id), () => setRevoking(null))} />
                )}
              </Fragment>
            ))}
          </ul>
        </Details>
      ))}
      <p className="cx-note">{TRAFFIC_NOTE}</p>
    </div>
  );
}

export default ConnectionsPanel;
