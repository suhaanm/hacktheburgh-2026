// The firm brief: one printable page built from the same three answers the Firm screens read (overview, roles, onboarding). Pure, so it is tested.
// Every figure is read from the data; the words around them are fixed. It says what it cannot show, and it never ranks a person.
import { compareShown, effectText, fmtNum, fmtShare, pct, roleGapLine } from "./model";
import type { WireOnboarding, WireOverview, WireRoles } from "./wire";

export const BRIEF_STATEMENT = "For coaching and onboarding, not for evaluating individuals.";

export const BRIEF_LIMITS: string[] = [
  "Intervals are 95% intervals from resampling people. Small groups have wide ones, and a wide interval means we cannot tell.",
  "Groups under 5 people are not compared, and a group figure never describes two or three individuals.",
  "The target on the onboarding curves is a design target the firm sets. It is a line to aim at, not a measured standard.",
  "A trend class is a prompt for a conversation. It is not a grade, and no list here is ranked.",
  "A real deployment would need a lawful basis and a clear notice to workers before any of this is shared.",
];

export interface BriefInsight { headline: string; effect: string | null; n: string }
export interface BriefRole { role: string; name: string; compared: boolean; people: string; gap: string; independence: string }
export interface BriefOnboarding { role: string; name: string; n: number; median: string; reached: string }

export interface Brief {
  statement: string;
  label: string;
  asOf: string | null;
  summary: string;
  insights: BriefInsight[];
  roles: BriefRole[];
  onboarding: BriefOnboarding[];
  target: string;
  limits: string[];
}

const nOf = (n: number, unit: string): string => `${n} ${n === 1 ? unit.replace(/s$/, "").replace(/^people$/, "person") : unit}`;

export function buildBrief(o: WireOverview, roles: WireRoles, onb: WireOnboarding, asOf: string | null, min = 5): Brief {
  const independence = (r: WireRoles["roles"][number]) => r.measures.find((m) => m.key === "independence");
  return {
    statement: BRIEF_STATEMENT,
    label: o.firm.label,
    asOf,
    summary: `${o.firm.users} people in ${o.firm.roles} roles. ${o.coverage.enough_data} of them have enough data for a trend.`,
    insights: o.top.slice(0, 7).map((i) => ({ headline: i.headline, effect: effectText(i.effect), n: nOf(i.n, i.n_unit) })),
    roles: roles.roles.map((r) => {
      const ind = independence(r);
      const shown = compareShown(r, min);
      return {
        role: r.role, name: r.name, compared: shown,
        people: `${r.n_expert} experts, ${r.n_junior} juniors`,
        gap: shown ? roleGapLine(ind, r.measures.find((m) => m.key === "time_vs_expert")) : "Not compared: fewer than 5 people in a group.",
        independence: shown && ind ? `experts ${fmtShare(ind.expert)}; juniors ${fmtShare(ind.junior)}` : "",
      };
    }),
    onboarding: onb.roles.map((r) => ({
      role: r.role, name: r.name, n: r.n,
      median: r.median_to_target ? fmtNum(r.median_to_target, onb.x_unit === "occurrences" ? "steps" : onb.x_unit) : "not reached by half yet",
      reached: fmtShare(r.reached_share),
    })),
    target: `${onb.target.label}: ${pct(onb.target.value)} of recent steps finished without help`,
    limits: BRIEF_LIMITS,
  };
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
/** "2026-11-09T09:00:00Z" -> "9 November 2026". Null when it cannot be read. */
export function longDate(iso: string | null | undefined): string | null {
  const m = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : null;
}
