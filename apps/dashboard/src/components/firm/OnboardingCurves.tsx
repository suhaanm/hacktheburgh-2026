import { Details } from "../ui";
import { Hint } from "../Hint";
import { nWord } from "./Badges";
import { LineBand, ticksFor } from "./LineBand";
import { fmtShare, pct, trimCurve } from "./model";
import type { OnboardingRole, WireOnboarding } from "./wire";
import type { AnalyticMeta } from "../../types";

const MIN_PEOPLE = 5;

/** One shared set of axes for every role, so the three panels read as one comparison. */
export function sharedDomain(roles: OnboardingRole[]): { x: [number, number]; xTicks: number[] } {
  const xs = roles.flatMap((r) => trimCurve(r.curve, MIN_PEOPLE).map((p) => p.x));
  const hi = xs.length ? Math.max(...xs) : 100;
  const top = Math.max(20, Math.ceil(hi / 20) * 20);
  return { x: [0, top], xTicks: ticksFor([0, top], 4) };
}

/** "Half reach the target by step 82", with the interval printed; or the honest alternative when half have not reached it. */
export function medianSentence(med: OnboardingRole["median_to_target"]): string {
  if (!med) return "Fewer than half have reached the target yet.";
  return `Half reach the target by step ${Math.round(med.value)}${med.ci ? ` (${Math.round(med.ci[0])} to ${Math.round(med.ci[1])})` : ""}.`;
}

/** One role: its name, the median sentence, n in the muted line, and a small chart (120 px high) on the shared axes. */
function Panel({ r, w, x, first, last }: { r: OnboardingRole; w: WireOnboarding; x: { x: [number, number]; xTicks: number[] }; first: boolean; last: boolean }) {
  const pts = trimCurve(r.curve, MIN_PEOPLE).map((p) => ({ x: p.x, y: p.y, lo: p.lo, hi: p.hi }));
  const med = r.median_to_target;
  return (
    <figure className="chart onb" aria-labelledby={`onb-${r.role}`}>
      <figcaption className="onb__head">
        <h3 id={`onb-${r.role}`} className="onb__name">{r.name}</h3>
        <p className="onb__sentence">{medianSentence(med)}</p>
        <p className="onb__meta num">n = {nWord(r.n, "people")}. Reached the target so far: {fmtShare(r.reached_share)}.</p>
      </figcaption>
      {pts.length < 2 ? (
        <div className="state state--inline" role="status">
          <p className="state__title">No curve yet</p>
          <p className="state__body">{r.reason ?? `Fewer than ${MIN_PEOPLE} people have been followed long enough, so no curve is drawn.`}</p>
        </div>
      ) : (
        <LineBand
          title={`Share of steps finished without help by step number, ${r.name}`} points={pts}
          xDomain={x.x} yDomain={[0, 1]} xTicks={x.xTicks} yTicks={[0, 0.5, 1]}
          formatX={(v) => String(v)} formatY={pct}
          target={{ value: w.target.value, label: first ? `${w.target.label} ${pct(w.target.value)}` : "" }}
          mark={med ? { x: med.value, ci: med.ci, label: `Median step at which people reach the target: ${Math.round(med.value)}` } : undefined}
          xLabel={last ? "Steps done in the role" : undefined} height={120}
        />
      )}
    </figure>
  );
}

/**
 * Onboarding-speed curves: for each role, the share of steps finished without help against how many steps the person has done, with the interval
 * band, and the target as a dashed line named a design target. The shaded vertical band is the interval on the median step at which people reach it.
 */
export function OnboardingCurves({ data }: { data: WireOnboarding; meta?: AnalyticMeta | null }) {
  const x = sharedDomain(data.roles);
  return (
    <div className="onb-wrap">
      <p className="onb__legend legend__item">
        <i className="sw sw--line sw--novice" />Share finished without help, 95% band, dashed: {data.target.label}
        <Hint label="About the design target">{data.target.note ?? "The target is a line the firm chooses. It is not a measured standard, and people differ."}</Hint>
      </p>
      <div className="onb-stack">
        {data.roles.map((r, i) => <Panel key={r.role} r={r} w={data} x={x} first={i === 0} last={i === data.roles.length - 1} />)}
      </div>
      <Details summary="How this was worked out">
        <p>{data.method ?? "Each curve follows people through their first steps in the role. The curve stops where fewer than 5 people remain in view, so it never describes two or three individuals."}</p>
        <p>The target is a design target the firm sets. It is a line to aim at, not a standard that anyone is measured against.</p>
      </Details>
    </div>
  );
}
