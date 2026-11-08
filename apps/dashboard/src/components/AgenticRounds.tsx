import type { ReactNode } from "react";
import { Details } from "./ui";
import { agenticRounds, barWords, halfFigure, type Round } from "../lib/agenticRounds";
import type { AnalyticMeta, EvalReport } from "../types";

/**
 * The computer-use rounds of the agent evaluation, side by side (an Evidence block, for reviewers; the words are concrete on purpose). One headline that says what the newest
 * round did and whether its pre-registered bar was met; one small table with a row per round (the configuration, the clean half, the bar, the injected half); gate versions,
 * seeds, stops and the one-line limits behind a disclosure. Read from `sections.agentic` of evals/report.json by `lib/agenticRounds.ts`; a report with no rounds shows nothing.
 */
type Sec = { meta?: AnalyticMeta } & Record<string, unknown>;

function Pass({ ok, children }: { ok: boolean | null; children: ReactNode }) {
  if (ok == null) return <span className="u-muted">{children}</span>;
  return <span className="pill pill--status" data-status={ok ? "ok" : "failed"}><span className="pill__glyph-char" aria-hidden="true">{ok ? "✓" : "✕"}</span>{children}</span>;
}

const cap = (t: string): string => `${t.charAt(0).toUpperCase()}${t.slice(1)}`;

function configShort(r: Round): string {
  // "openai (planner gpt-5.5, fast gpt-5.4-mini, computer use gpt-5.5)" is a long line; the page shows the provider and says the rest behind the disclosure.
  const m = /\(([^)]*)\)/.exec(r.config);
  return m ? m[1] : r.config;
}

export function AgenticRounds({ rep }: { rep: EvalReport }) {
  const s = ((rep.sections as unknown as Record<string, unknown>).agentic ?? null) as Sec | null;
  const data = agenticRounds(s);
  if (!data) return null;
  const meta = s?.meta ?? null;
  const injectedNote = (() => {
    const ho = (s as { heldout?: { injected?: { owner_note?: unknown } } } | null)?.heldout?.injected;
    return typeof ho?.owner_note === "string" ? ho.owner_note : null;
  })();
  return (
    <section className="ev-block" id="rounds" aria-labelledby="rounds-h">
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <p className="t-label">Does the computer-use agent finish the work?</p>
        <h2 className="ev-claim" id="rounds-h">{data.headline}</h2>
      </div>

      <div className="table-wrap">
        <table className="table">
          <caption className="u-muted" style={{ textAlign: "left", paddingBottom: "var(--space-2)" }}>Held-out rounds, one row each. Each measures a different configuration; they are never pooled.</caption>
          <thead>
            <tr>
              <th scope="col">Round</th>
              <th scope="col" className="num">Completed with correct inputs</th>
              <th scope="col">Pre-registered bar</th>
              <th scope="col" className="num">Injected pages paused</th>
            </tr>
          </thead>
          <tbody>
            {data.rounds.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.label}</strong>, {r.provider}
                </td>
                <td className="num">{r.clean ? <>{halfFigure(r.clean)}</> : <span className="u-muted">not run</span>}</td>
                <td><Pass ok={r.clean ? r.clean.barMet : null}>{barWords(r.clean)}</Pass></td>
                <td className="num">{r.injected ? halfFigure(r.injected) : <span className="u-muted">not run</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="ev-note">Intervals are 95% Wilson intervals. The clean half asks for all three calculators filled with correct inputs, judged by code. The injected half asks whether the detector paused a page that carries text aimed at an AI.</p>

      <Details wide summary="Gate versions, seeds and stops">
        <div className="table-wrap">
          <table className="table" style={{ minWidth: 900 }}>
            <thead>
              <tr>
                <th scope="col">Round</th>
                <th scope="col">Models</th>
                <th scope="col">Gate build</th>
                <th scope="col" className="num">Seeds (clean, injected)</th>
                <th scope="col" className="num">False claims (clean)</th>
                <th scope="col" className="num">Unexpected gate stops</th>
              </tr>
            </thead>
            <tbody>
              {data.rounds.map((r) => (
                <tr key={r.id}>
                  <td>{r.label}</td>
                  <td>{configShort(r)}</td>
                  <td>{r.gateVersion ? <><code>{r.gateVersion}</code> {r.gateOk === true ? "matches the build frozen for this round" : r.gateOk === false ? "does not match the frozen build" : ""}</> : <span className="u-muted">not recorded</span>}</td>
                  <td className="num">{r.clean?.seed ?? "n/a"}, {r.injected?.seed ?? "n/a"}</td>
                  <td className="num">{r.falseClaims ?? "n/a"}</td>
                  <td className="num">{r.unexpectedStops ?? "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ev-note">Stops by the gate are harness or gate-tuning findings, listed apart from model failures. {injectedNote ? cap(injectedNote) : ""}</p>
        {meta?.note ? <p className="ev-note">{cap(meta.note)}</p> : null}
      </Details>
    </section>
  );
}
