import { Details } from "../ui";
import { Hint } from "../Hint";
import { FirmBadge, nWord } from "./Badges";
import { LineBand, ticksFor } from "./LineBand";
import { fmtNum, fmtShare, pct, trimCurve } from "./model";
import type { OnboardingRole, WireOnboarding } from "./wire";
import type { AnalyticMeta } from "../../types";

const MIN_PEOPLE = 5;

/** One shared set of axes for every role, so the three panels read as one comparison. */
export function sharedDomain(roles: OnboardingRole[]): { x: [number, number]; xTicks: number[] } {
  const xs = roles.flatMap((r) => trimCurve(r.curve, MIN_PEOPLE).map((p) => p.x));
  const hi = xs.length ? Math.max(...xs) : 100;
  const top = Math.max(20, Math.ceil(hi / 20) * 20);
  return { x: [0, top], xTicks: ticksFor([0, top], 6) };
}

function Panel({ r, w, x, meta }: { r: OnboardingRole; w: WireOnboarding; x: { x: [number, number]; xTicks: number[] }; meta: AnalyticMeta | null }) {
  const pts = trimCurve(r.curve, MIN_PEOPLE).map((p) => ({ x: p.x, y: p.y, lo: p.lo, hi: p.hi }));
  const med = r.median_to_target;
  return (
    <figure className="chart onb" aria-labelledby={`onb-${r.role}`}>
      <figcaption className="onb__head">
        <h3 id={`onb-${r.role}`} className="onb__name">{r.name}</h3>
        <FirmBadge meta={meta} />
      </figcaption>
      {pts.length < 2 ? (
        <div className="state state--inline" role="status">
          <span className="state__mark" aria-hidden="true" />
          <p className="state__title">No curve yet</p>
          <p className="state__body">{r.reason ?? `Fewer than ${MIN_PEOPLE} people have been followed long enough, so no curve is drawn.`}</p>
        </div>
      ) : (
        <LineBand
          title={`Share of steps finished without help by step number, ${r.name}`} points={pts}
          xDomain={x.x} yDomain={[0, 1]} xTicks={x.xTicks} yTicks={[0, 0.25, 0.5, 0.75, 1]}
          formatX={(v) => String(v)} formatY={pct}
          target={{ value: w.target.value, label: `${w.target.label} ${pct(w.target.value)}` }}
          mark={med ? { x: med.value, ci: med.ci, label: `Median step at which people reach the target: ${Math.round(med.value)}` } : undefined}
          xLabel="Steps done in the role" height={210}
        />
      )}
      <dl className="onb__nums">
        <div><dt>People followed</dt><dd>n = {nWord(r.n, "people")}</dd></div>
        <div><dt>Median step to the target</dt><dd>{med ? fmtNum(med, "steps") : "not reached by half yet"}</dd></div>
        <div><dt>Reached it so far</dt><dd>{fmtShare(r.reached_share)}</dd></div>
      </dl>
    </figure>
  );
}

/**
 * Onboarding-speed curves: for each role, the share of steps finished without help against how many steps the person has done, with the interval
 * band, and the target as a dashed line named a design target. The shaded vertical band is the interval on the median step at which people reach it.
 */
export function OnboardingCurves({ data, meta }: { data: WireOnboarding; meta: AnalyticMeta | null }) {
  const x = sharedDomain(data.roles);
  return (
    <div className="onb-wrap">
      <ul className="legend onb__legend" aria-label="How to read the curves">
        <li className="legend__item"><i className="sw sw--line sw--novice" />Share finished without help in recent steps</li>
        <li className="legend__item"><i className="sw sw--hatch sw--novice" />95% interval</li>
        <li className="legend__item"><i className="sw sw--dashed sw--muted" />{data.target.label}</li>
        <li className="legend__item"><i className="sw sw--accent" />Median step at which the target is reached, with its interval</li>
        <Hint label="About the design target">{data.target.note ?? "The target is a line the firm chooses. It is not a measured standard, and people differ."}</Hint>
      </ul>
      <div className="onb-grid">
        {data.roles.map((r) => <Panel key={r.role} r={r} w={data} x={x} meta={meta} />)}
      </div>
      <Details summary="How this was worked out">
        <p>{data.method ?? "Each curve follows people through their first steps in the role. The curve stops where fewer than 5 people remain in view, so it never describes two or three individuals."}</p>
        <p>The target is a design target the firm sets. It is a line to aim at, not a standard that anyone is measured against.</p>
      </Details>
    </div>
  );
}
