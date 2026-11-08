import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, api } from "../../api";
import { ErrorState, Loading } from "../../components/common";
import { AdminSees } from "../../components/yourdata/AdminSees";
import { Measured } from "../../components/yourdata/Measured";
import { OriginBadge, SectionSource } from "../../components/needsyou/Origin";
import { Remembers } from "../../components/yourdata/Remembers";
import { SentLink } from "../../components/yourdata/SentLink";
import { Switches } from "../../components/yourdata/Switches";
import { YdSection } from "../../components/yourdata/YdSection";
import { useToast } from "../../components/Toasts";
import { ConfirmRow } from "../../components/ui";
import { useLoad } from "../../hooks";
import { captureOn, setCapture } from "../../lib/memory";
import { useRoute } from "../../router";
import { useAppState } from "../../store";
import { downloadText, exportLedger, deleteLedger, loadLedger } from "../Growth/data";
import { loadSharing } from "../Home/data";
import { desktopBridge, type DesktopSettings } from "../Settings/bridge";
import { awarenessBridge, type AwarenessChoice, type AwarenessState } from "./awareness";
import { deleteEverything } from "./data";
import { YD_SECTIONS, YD_TITLE, dataHeadline, deleteAllText, deleteResultText, factLine, memoryItems, ydSectionOf, type YdSection as Id } from "./model";
import "../../components/kc.css";
import "../../components/yourdata/yourdata.css";

/**
 * Your data: what Knack remembers, measures and has sent, with a delete beside each, in five sections (the first open). "Delete everything" is on the
 * screen itself: the button, then one confirm that says exactly what is cleared. No file path is printed; the file's location is behind a copy button.
 */
export default function YourData() {
  const route = useRoute();
  const toast = useToast();
  const me = useAppState().person;
  const want = ydSectionOf(route.query.get("section"));
  const mem = useLoad(() => api.memory(), []);
  const rules = useLoad(() => api.proposals(), []);
  const ledger = useLoad(() => api.privacyLedger(), []);
  const sharing = useLoad(() => loadSharing(me), [me]);
  const steps = useLoad(() => loadLedger("going", false), []);
  const [open, setOpen] = useState<Set<Id>>(() => new Set<Id>([want ?? "remembers"]));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const awareness = useMemo(() => awarenessBridge(), []);
  const desktop = useMemo(() => desktopBridge(), []);
  const [glance, setGlance] = useState<AwarenessState | null>(null);
  const [dset, setDset] = useState<DesktopSettings | null>(null);
  useEffect(() => { awareness?.state().then(setGlance, () => setGlance(null)); }, [awareness]);
  useEffect(() => { desktop?.getSettings().then(setDset, () => setDset(null)); }, [desktop]);

  // An address that names a section opens it and brings it into view.
  useEffect(() => {
    if (!want) return;
    setOpen((s) => (s.has(want) ? s : new Set(s).add(want)));
    window.setTimeout(() => document.getElementById(`yd-${want}`)?.scrollIntoView?.({ block: "start" }), 60);
  }, [want]);

  if (mem.status === "error" && !mem.data) return <div className="page page--read kc-page"><ErrorState error={mem.error} retry={mem.reload} what="what Knack remembers" /></div>;
  if (!mem.data) return <div className="page page--read kc-page"><Loading label="Loading your data" /></div>;
  const m = mem.data;
  const items = memoryItems(m);
  const capture = captureOn(m.sections);
  const entries = ledger.data ?? [];
  const counts = steps.data?.counts ?? { assist: 0, delegated: 0, automation: 0 };
  const stepTotal = counts.assist + counts.delegated + counts.automation;
  const reloadAll = () => { mem.reload(); rules.reload(); ledger.reload(); steps.reload(); };
  const toggle = (id: Id) => setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const onCapture = async (on: boolean) => {
    setBusy(true); setErr(null);
    try {
      await api.putMemory(setCapture(m.markdown, on), m.revision);
      toast({ tone: "success", text: on ? "Capture is on." : "Capture is off.", detail: on ? "Times only. No page text, no URLs." : "Nothing more is recorded about when you are active." });
      mem.reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) { toast({ tone: "error", text: "The file changed while you were deciding.", detail: "It is reloaded. Check the switch and try again." }); mem.reload(); }
      else setErr(e instanceof ApiError ? e.message : "Could not change capture. Nothing was changed.");
    } finally { setBusy(false); }
  };
  const onGlance = (c: AwarenessChoice) => {
    setErr(null);
    awareness?.setConsent(c).then(setGlance, () => setErr("Could not change that. Nothing was changed."));
  };
  const onDesktop = (patch: Partial<DesktopSettings>) => {
    if (!desktop) return;
    const before = dset;
    setDset((d) => ({ ...(d ?? {}), ...patch }));
    desktop.patchSettings(patch).then((r) => { if (r && typeof r === "object") setDset(r as DesktopSettings); }, () => { setDset(before); setErr("Could not change that. Nothing was changed."); });
  };

  const exampleSteps = steps.source === "demo";
  const del = deleteAllText({ memoryLines: items.length, steps: stepTotal, calls: entries.length, person: !!me });
  const doDelete = async () => {
    setBusy(true); setErr(null);
    try {
      const parts = await deleteEverything({ memory: m, person: me, example: exampleSteps });
      setResult(deleteResultText(parts));
      setConfirm(false);
      toast({ tone: parts.every((p) => p.ok) ? "success" : "error", text: parts.every((p) => p.ok) ? "Deleted." : "Some of it was not deleted.", detail: deleteResultText(parts) });
      reloadAll();
    } finally { setBusy(false); }
  };

  const f = { lines: items.length, rules: (rules.data ?? []).filter((p) => p.status === "proposed").length, capture, entries, steps: stepTotal, shared: sharing.data ? sharing.data.items.length : null };
  const sources = [mem, ledger, steps, sharing];
  const body: Record<Id, ReactNode> = {
    remembers: <><SectionSource why={mem.why} /><Remembers memory={m} proposals={rules.data ?? []} onChanged={() => { mem.reload(); rules.reload(); }} /></>,
    measured: <><SectionSource why={steps.why} /><Measured capture={capture} view={steps.data} example={exampleSteps} onExport={async () => { const x = await exportLedger("going", exampleSteps); downloadText(x.filename.replace("understudy", "knack"), x.text); }} onDelete={async () => { const n = await deleteLedger("going", exampleSteps); steps.reload(); return n; }} /></>,
    sent: <SentLink />,
    "admin-sees": sharing.data ? <><SectionSource why={sharing.why} /><AdminSees sharing={sharing.data} /></> : <div className="yd-body"><Loading label="Loading what your admin can see" /></div>,
    switches: <Switches capture={capture} onCapture={(on) => void onCapture(on)} busy={busy} glance={awareness ? glance : null} onGlance={onGlance} desktop={desktop ? dset : null} onDesktop={onDesktop} error={err} />,
  };

  return (
    <div className="page page--read kc-page">
      <div className="kc-head">
        <h1 className="kc-title">Your data</h1>
        <OriginBadge sources={sources} />
      </div>
      <p className="kc-headline" data-testid="headline">{dataHeadline({ lines: items.length, capture })}</p>

      <div className="yd">
        {YD_SECTIONS.map((id) => (
          <YdSection key={id} id={id} title={YD_TITLE[id]} fact={factLine(id, f)} open={open.has(id)} onToggle={() => toggle(id)}>{body[id]}</YdSection>
        ))}
      </div>

      <div className="yd-delete">
        {result && <p className="note" role="status" data-testid="delete-result">{result}</p>}
        {confirm ? (
          <ul className="kc-list"><ConfirmRow question={del.question} consequence={del.consequence} confirmLabel={busy ? "Deleting" : "Delete everything"} busy={busy} onConfirm={() => void doDelete()} onCancel={() => setConfirm(false)} /></ul>
        ) : (
          <div><button type="button" className="btn btn--secondary" onClick={() => { setResult(null); setConfirm(true); }}>Delete everything</button></div>
        )}
      </div>
    </div>
  );
}
