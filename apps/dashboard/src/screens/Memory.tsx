import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { EmptyState, ErrorState, Loading, PageHead } from "../components/common";
import { useToast } from "../components/Toasts";
import { Details } from "../components/ui";
import { Hint } from "../components/Hint";
import { captureOn, removeLineText, replaceLineText, setCapture } from "../lib/memory";
import type { Memory as MemoryT, RuleProposal } from "../types";

interface Row { no: number; raw: string; kind: "front" | "h" | "item" | "blank" | "text"; id: string | null; text: string; note: string | null }

/** Notes in the engine's file look like "id:l_ab12 | why". The id is plumbing; show only the why. */
const cleanNote = (n: string | null) => { const c = (n ?? "").replace(/^id:\S+\s*\|?\s*/, "").trim(); return c || null; };

function rowsOf(m: MemoryT): Row[] {
  const byText = new Map<string, { id: string; note: string | null }>();
  for (const lines of Object.values(m.sections)) for (const l of lines) byText.set(l.text.trimEnd(), { id: l.id, note: cleanNote(l.note) });
  const out: Row[] = [];
  let front = 0;
  m.markdown.replace(/\n$/, "").split("\n").forEach((raw, i) => {
    if (raw.trim() === "---") { front++; out.push({ no: i + 1, raw, kind: "front", id: null, text: raw, note: null }); return; }
    if (front === 1) { out.push({ no: i + 1, raw, kind: "front", id: null, text: raw, note: null }); return; }
    if (/^##\s/.test(raw)) { out.push({ no: i + 1, raw, kind: "h", id: null, text: raw.replace(/^##\s+/, ""), note: null }); return; }
    const b = /^\s*[-*]\s+(.*?)(?:\s*<!--\s*(.*?)\s*-->)?\s*$/.exec(raw);
    if (b) { const hit = byText.get(b[1].trimEnd()); out.push({ no: i + 1, raw, kind: "item", id: hit?.id ?? null, text: b[1], note: hit ? hit.note : cleanNote(b[2] ?? null) }); return; }
    out.push({ no: i + 1, raw, kind: raw.trim() ? "text" : "blank", id: null, text: raw, note: null });
  });
  return out;
}

/** A long absolute path would push the page sideways; keep the tail and put the whole thing in the tooltip. */
function shortPath(p: string): string {
  const i = p.indexOf(".understudy");
  if (i >= 0) return `~/${p.slice(i)}`;
  const parts = p.split("/").filter(Boolean);
  return parts.length > 2 ? `…/${parts.slice(-2).join("/")}` : p;
}

export default function Memory() {
  const mem = useLoad(() => api.memory(), []);
  const props = useLoad(() => api.proposals(), []);
  const toast = useToast();
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [draft, setDraft] = useState("");
  const [conflict, setConflict] = useState<{ latest: MemoryT } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ no: number; old: string; value: string } | null>(null);
  const [forget, setForget] = useState<number | null>(null);
  const [hot, setHot] = useState<string | null>(null);

  useEffect(() => { if (mem.data && mode === "read") setDraft(mem.data.markdown); }, [mem.data, mode]);
  useEffect(() => { if (!hot) return; const t = window.setTimeout(() => setHot(null), 4000); return () => window.clearTimeout(t); }, [hot]);
  const rows = useMemo(() => (mem.data ? rowsOf(mem.data) : []), [mem.data]);

  if (mem.status === "error" && !mem.data) return <div className="page"><ErrorState error={mem.error} retry={mem.reload} what="your memory file" /></div>;
  if (!mem.data) return <div className="page page--read"><Loading label="Loading your memory file" /></div>;
  const m = mem.data;

  const save = async (markdown: string, base: number, okText: string, changed?: string) => {
    setBusy(true); setErr(null);
    try {
      await api.putMemory(markdown, base);
      setConflict(null); setEdit(null);
      if (changed) setHot(changed);
      toast({ tone: "success", text: okText });
      setMode("read");
      mem.reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // The file moved on. Keep the worker's text; offer to re-submit it on top of the new revision. The worker's edit wins.
        try { const latest = await api.memory(); setConflict({ latest: latest.data }); } catch { setErr("The file changed and the new version could not be loaded. Reload the page."); }
      } else setErr(e instanceof ApiError ? e.message : "Could not save. Your text is still here.");
    } finally { setBusy(false); }
  };

  const saveLine = () => {
    if (!edit) return;
    const md = replaceLineText(m.markdown, edit.old, edit.value.trim());
    if (!md) { setErr("That line is not in the file any more. Reload and try again."); return; }
    void save(md, m.revision, "Line saved.", edit.value.trim());
  };
  const doForget = async (row: Row) => {
    setBusy(true); setErr(null);
    try {
      if (row.id) await api.forget(row.id);
      else { const md = removeLineText(m.markdown, row.text); if (!md) throw new ApiError(404, "gone", "That line is not in the file any more."); await api.putMemory(md, m.revision); }
      toast({ tone: "success", text: "Forgotten.", detail: "The line is gone from the file and from how Understudy behaves." });
      setForget(null); mem.reload();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not remove it. Try again."); }
    finally { setBusy(false); }
  };

  const capture = captureOn(m.sections);
  const toggleCapture = async () => {
    setBusy(true); setErr(null);
    try {
      await api.putMemory(setCapture(m.markdown, !capture), m.revision);
      toast({ tone: "success", text: capture ? "Capture is off." : "Capture is on.", detail: capture ? "Nothing more is recorded about when you are active." : "Times only. No page text, no URLs." });
      mem.reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) { toast({ tone: "error", text: "The file changed while you were deciding.", detail: "It is reloaded. Check the line and try again." }); mem.reload(); }
      else setErr(e instanceof ApiError ? e.message : "Could not change capture. Try again.");
    } finally { setBusy(false); }
  };
  const itemCount = rows.filter((r) => r.kind === "item").length;
  const pending = (props.data ?? []).filter((p) => p.status === "proposed");
  const past = (props.data ?? []).filter((p) => p.status !== "proposed");

  return (
    <div className="page page--read">
      <PageHead
        eyebrow="Memory"
        title="What Understudy knows about you"
        lede={<>One Markdown file on this device, owned by you. Only your own actions and approvals can change it.<Hint label="About who can change it">Text from a web page or a tool never can.</Hint></>}
        aside={<span className="pill pill--path"><b>rev {m.revision}</b>{shortPath(m.path)}</span>}
      />

      <div className="row capture" role="group" aria-label="Capture">
        <span className="pill" data-capture={capture}><span className="pill__dot" style={{ ["--_c" as string]: capture ? "var(--good)" : "var(--muted)" }} aria-hidden="true" />{capture ? "Capture is on" : "Capture is off"}</span>
        <span className="note">{capture ? "Only the times you are active are recorded. No page text, no URLs." : "Nothing about when you are active is recorded."}</span>
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={toggleCapture}>{capture ? "Turn off" : "Turn on"}</button>
      </div>

      <section className="hero" aria-labelledby="file-h">
        <div className="hero__bar">
          <h2 className="u-sr-only" id="file-h">The memory file</h2>
          <div className="segmented" role="group" aria-label="View">
            <button type="button" aria-pressed={mode === "read"} onClick={() => { setMode("read"); setConflict(null); setErr(null); }}>Read</button>
            <button type="button" aria-pressed={mode === "edit"} onClick={() => { setDraft(m.markdown); setMode("edit"); setEdit(null); }}>Edit as text</button>
          </div>
        </div>

        {conflict && (
          <div className="note note--warn conflict" role="alert">
            <p><b>The file changed while you were editing.</b> It is now revision {conflict.latest.revision}. Your version is kept below, nothing is lost.</p>
            <div className="row">
              <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => save(draft, conflict.latest.revision, "Saved. Your version replaced the newer one.")}>Save mine over it</button>
              <button type="button" className="btn btn--secondary btn--sm" onClick={() => { setDraft(conflict.latest.markdown); setConflict(null); mem.reload(); }}>Load the new version</button>
            </div>
          </div>
        )}

        {mode === "read" ? (
          <div className="memfile">
            <div className="memfile__bar"><span>{shortPath(m.path)}<Hint label="Full path of the file"><code>{m.path}</code></Hint></span><span>revision {m.revision} · {rows.filter((r) => r.kind === "item").length} lines</span></div>
            <div className="memfile__body">
              {rows.map((r) => {
                if (edit && edit.no === r.no) {
                  return (
                    <div key={r.no} className="memline-edit">
                      <label className="u-sr-only" htmlFor={`ml-${r.no}`}>Edit line {r.no}</label>
                      <input id={`ml-${r.no}`} className="input" value={edit.value} autoFocus onChange={(e) => setEdit({ ...edit, value: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") saveLine(); if (e.key === "Escape") setEdit(null); }} />
                      <div className="row"><button type="button" className="btn btn--primary btn--sm" disabled={busy || !edit.value.trim()} onClick={saveLine}>Save line</button><button type="button" className="btn btn--quiet btn--sm" onClick={() => setEdit(null)}>Cancel</button></div>
                    </div>
                  );
                }
                return (
                  <div key={r.no} className={`memfile__line${hot && r.text === hot ? " memfile__line--new" : ""}`}>
                    <span className="memfile__no" aria-hidden="true">{r.no}</span>
                    <span className={`memfile__text ${r.kind === "h" ? "memfile__h" : r.kind === "front" ? "memfile__mark" : ""}`}>
                      {r.kind === "h" ? `## ${r.text}` : r.kind === "item" ? <><span className="memfile__mark">- </span>{r.text}{r.note && <span className="memfile__tag">   {r.note}</span>}</> : r.text || " "}
                    </span>
                    {r.kind === "item" ? (
                      <span className="memfile__actions">
                        {forget === r.no ? (
                          <>
                            <button type="button" className="btn btn--danger btn--sm" disabled={busy} onClick={() => doForget(r)}>Forget it</button>
                            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setForget(null)}>Keep</button>
                          </>
                        ) : (
                          <>
                            <button type="button" className="btn btn--quiet btn--sm" onClick={() => { setForget(null); setEdit({ no: r.no, old: r.text, value: r.text }); }} aria-label={`Edit line ${r.no}`}>Edit</button>
                            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setForget(r.no)} aria-label={`Forget line ${r.no}`}>Forget</button>
                          </>
                        )}
                      </span>
                    ) : <span />}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="stack">
            <label className="u-sr-only" htmlFor="memtext">Memory file as Markdown</label>
            <textarea id="memtext" className="memtext" value={draft} spellCheck={false} onChange={(e) => setDraft(e.target.value)} />
            <p className="note">Keep the headings. Lines starting with a dash are the items. A comment like &lt;!-- note --&gt; at the end of a line is kept as that line's note.</p>
            <div className="row">
              <button type="button" className="btn btn--primary" disabled={busy || draft === m.markdown} onClick={() => save(draft, m.revision, "Memory file saved.")}>{busy ? "Saving" : "Save file"}</button>
              <button type="button" className="btn btn--quiet" onClick={() => { setDraft(m.markdown); setMode("read"); }}>Discard changes</button>
            </div>
          </div>
        )}
        {err && <p className="field__error" role="alert">{err}</p>}
        {itemCount === 0 && mode === "read" && <EmptyState title="Your memory file is empty" body="Choose a role in set-up and Understudy writes the first lines here. Everything in it stays on this device." action={<a className="btn btn--secondary" href="#/onboarding">Go to set-up</a>} />}
      </section>

      <hr className="rule" />

      <section className="section" aria-labelledby="rules-h">
        <div className="section__head">
          <h2 className="section__title" id="rules-h">Rules Understudy would like to add</h2>
          <p className="section__sub">After three matching corrections it proposes a rule. Nothing turns on until you approve it.<Hint label="About working-method rules">A working-method rule must first match expert results in shadow runs.</Hint></p>
        </div>
        {props.status === "loading" && !props.data ? <Loading label="Loading rule proposals" /> : props.status === "error" && !props.data ? <ErrorState error={props.error} retry={props.reload} what="rule proposals" /> : (
          <>
            {pending.length === 0 ? <EmptyState title="No rules waiting" body="Correct the same thing three times and a proposed rule will appear here." /> : (
              <div className="rules">{pending.map((p) => <RuleRow key={p.id} p={p} onDone={() => { props.reload(); mem.reload(); }} />)}</div>
            )}
            {past.length > 0 && (
              <Details summary={`Rule history (${past.length})`} wide>
                <div className="rules">{past.map((p) => <RuleRow key={p.id} p={p} onDone={() => undefined} />)}</div>
              </Details>
            )}
          </>
        )}
      </section>
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
    catch (e) { setErr(e instanceof ApiError ? e.message : "That did not save. Try again."); }
    finally { setBusy(false); }
  };
  return (
    <div className="rule-row">
      <div className="rule-row__head">
        <span className="rule-row__text">{p.rule}</span>
        <span className="pill">{p.kind === "procedure" ? "Working method" : "Preference"}</span>
        {p.status !== "proposed" && <span className="pill"><b>v{p.version}</b>{p.status}</span>}
      </div>
      <p className="note">Seen in {p.evidence_count} of your corrections.{p.kind === "procedure" ? (p.shadow_match == null ? " Not yet tested against expert results." : ` ${Math.round(p.shadow_match * 100)}% of shadow runs matched expert results.`) : ""}</p>
      {err && <p className="field__error" role="alert">{err}</p>}
      {p.status === "proposed" && (
        <div className="row">
          <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => go("approve")}>Approve rule</button>
          <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => go("reject")}>Reject</button>
        </div>
      )}
    </div>
  );
}
