import { useState } from "react";
import { ApiError, api } from "../../api";
import { replaceLineText } from "../../lib/memory";
import { memoryItems, type MemItem } from "../../screens/YourData/model";
import type { Memory, RuleProposal } from "../../types";
import { ConfirmRow, Details } from "../ui";
import { useToast } from "../Toasts";

const SHOWN = 3;

/**
 * What Knack remembers: the memory file as plain lines, a few at a time, each with Edit and Forget (Forget asks once, inline: "Forget it" or "Keep").
 * Only the worker's own actions and approvals change the file. The file's location is behind a copy button, never printed. A rule Knack would like to
 * add waits here for a click; nothing turns on until it is approved.
 */
export function Remembers({ memory: m, proposals, onChanged }: { memory: Memory; proposals: RuleProposal[]; onChanged: () => void }) {
  const toast = useToast();
  const items = memoryItems(m);
  const [all, setAll] = useState(false);
  const [edit, setEdit] = useState<{ id: string; old: string; value: string } | null>(null);
  const [forget, setForget] = useState<string | null>(null);
  const [whole, setWhole] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const shown = all ? items.slice(0, 200) : items.slice(0, SHOWN);
  const waiting = (Array.isArray(proposals) ? proposals : []).filter((p) => p && p.status === "proposed");
  const fail = (e: unknown, fallback: string) => setErr(e instanceof ApiError ? e.message : fallback);

  const saveLine = async () => {
    if (!edit) return;
    const md = replaceLineText(m.markdown, edit.old, edit.value.trim());
    if (!md) { setErr("That line is not in the file any more. Nothing was changed."); return; }
    setBusy(true); setErr(null);
    try { await api.putMemory(md, m.revision); setEdit(null); toast({ tone: "success", text: "Line saved." }); onChanged(); }
    catch (e) { fail(e, "Could not save. Your text is still here."); if (e instanceof ApiError && e.status === 409) onChanged(); }
    finally { setBusy(false); }
  };
  const doForget = async (it: MemItem) => {
    setBusy(true); setErr(null);
    try { await api.forget(it.id); setForget(null); toast({ tone: "success", text: "Forgotten.", detail: "The line is gone from the file and from how Knack behaves." }); onChanged(); }
    catch (e) { fail(e, "Could not remove it. Nothing was changed."); }
    finally { setBusy(false); }
  };
  const saveWhole = async () => {
    if (whole === null) return;
    setBusy(true); setErr(null);
    try { await api.putMemory(whole, m.revision); setWhole(null); toast({ tone: "success", text: "Memory file saved." }); onChanged(); }
    catch (e) {
      if (e instanceof ApiError && e.status === 409) { setErr("The file changed while you were editing. Your text is kept below. Reload it, or save yours over it."); onChanged(); }
      else fail(e, "Could not save. Your text is still here.");
    } finally { setBusy(false); }
  };
  const copyWhere = async () => {
    try { await navigator.clipboard.writeText(m.path); toast({ tone: "success", text: "Copied the location." }); }
    catch { toast({ tone: "error", text: "Could not copy.", detail: "Nothing was changed." }); }
  };

  return (
    <div className="yd-body" data-testid="remembers">
      <p className="kc-sub" data-testid="only-you">Stored on this Mac. Only you can change it.</p>
      {items.length === 0 ? (
        <div className="kc-empty"><h2>Nothing remembered yet.</h2><p>Set up again to write the first lines.</p></div>
      ) : (
        <ul className="kc-list" aria-label="What Knack remembers">
          {shown.map((it) => forget === it.id ? (
            <ConfirmRow key={it.id} question="Forget this line?" consequence={it.text} confirmLabel={busy ? "Forgetting" : "Forget it"} busy={busy} onConfirm={() => void doForget(it)} onCancel={() => setForget(null)} />
          ) : edit?.id === it.id ? (
            <li key={it.id} className="yd-line yd-line--edit">
              <label className="u-sr-only" htmlFor={`ml-${it.id}`}>Edit this line</label>
              <input id={`ml-${it.id}`} className="input" value={edit.value} autoFocus onChange={(e) => setEdit({ ...edit, value: e.target.value })}
                onKeyDown={(e) => { if (e.key === "Enter") void saveLine(); if (e.key === "Escape") setEdit(null); }} />
              <span className="row"><button type="button" className="btn btn--primary btn--sm" disabled={busy || !edit.value.trim()} onClick={() => void saveLine()}>Save line</button><button type="button" className="btn btn--secondary btn--sm" onClick={() => setEdit(null)}>Cancel</button></span>
            </li>
          ) : (
            <li key={it.id} className="yd-line" data-section={it.section} tabIndex={0}>
              <span className="yd-line__text">{it.text}{it.note && <span className="yd-line__note"> {it.note}</span>}</span>
              <span className="yd-line__actions">
                <button type="button" className="btn btn--quiet btn--sm" aria-label={`Edit: ${it.text}`} onClick={() => { setForget(null); setEdit({ id: it.id, old: it.text, value: it.text }); }}>Edit</button>
                <button type="button" className="btn btn--quiet btn--sm" aria-label={`Forget: ${it.text}`} onClick={() => { setEdit(null); setForget(it.id); }}>Forget</button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {items.length > SHOWN && <div><button type="button" className="btn btn--secondary btn--sm" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${items.length}`}</button></div>}
      {all && items.length > 200 && <p className="kc-sub">The first 200 of {items.length} lines are shown. Edit as text has them all.</p>}
      {err && <p className="kc-error" role="alert">{err}</p>}

      <Details summary={waiting.length > 0 ? `More (${waiting.length} ${waiting.length === 1 ? "rule" : "rules"} waiting)` : "More"} defaultOpen={whole !== null}>
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {waiting.length > 0 && (
            <div className="yd-rules" data-testid="rules">
              <p className="kc-label">Rules Knack would like to add</p>
              {waiting.map((p) => <RuleRow key={p.id} p={p} onDone={onChanged} />)}
            </div>
          )}
          {whole === null ? (
            <div className="row">
              <button type="button" className="btn btn--secondary btn--sm" onClick={() => setWhole(m.markdown)}>Edit as text</button>
              <button type="button" className="btn btn--secondary btn--sm" onClick={() => void copyWhere()}>Copy location</button>
            </div>
          ) : (
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              <label className="u-sr-only" htmlFor="memtext">Memory file as text</label>
              <textarea id="memtext" className="memtext" value={whole} spellCheck={false} onChange={(e) => setWhole(e.target.value)} />
              <p className="kc-sub">Keep the headings. Lines starting with a dash are the items.</p>
              <div className="row">
                <button type="button" className="btn btn--primary btn--sm" disabled={busy || whole === m.markdown} onClick={() => void saveWhole()}>{busy ? "Saving" : "Save file"}</button>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => { setWhole(null); setErr(null); }}>Discard changes</button>
              </div>
            </div>
          )}
        </div>
      </Details>
    </div>
  );
}

function RuleRow({ p, onDone }: { p: RuleProposal; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async (a: "approve" | "reject") => {
    setBusy(true); setErr(null);
    try { await api.decideProposal(p.id, a); toast({ tone: "success", text: a === "approve" ? "Rule approved and written to your file." : "Rule rejected.", detail: p.rule }); onDone(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "That did not save. Nothing was changed."); }
    finally { setBusy(false); }
  };
  return (
    <div className="yd-rule">
      <p className="yd-rule__text"><b>{p.rule}</b></p>
      <p className="kc-sub">Seen in {p.evidence_count} of your corrections.{p.kind === "procedure" ? (p.shadow_match == null ? " Not yet tested against expert results." : ` ${Math.round(p.shadow_match * 100)}% of practice runs matched expert results.`) : ""}</p>
      {err && <p className="kc-error" role="alert">{err}</p>}
      <div className="row">
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => void go("approve")}>Approve rule</button>
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => void go("reject")}>Reject</button>
      </div>
    </div>
  );
}
