// Pure words for the worker home: the title, the week label and the one line about repeated work. Numbers come from the data; the words are fixed.
import type { WireWorker } from "../../components/firm/wire";
import { APP_NAME } from "../../brand";

const COUNT_WORD = ["No", "One", "Two", "Three"];

/** The page title. A week with nothing to say says so plainly, and a new person is told what is happening instead of shown an empty page. */
export function homeTitle(status: string, shown: number): string {
  if (status === "onboarding") return `${APP_NAME} is getting to know your work`;
  if (status === "no_data") return "There is nothing to show yet";
  if (status === "stale") return "These numbers are not fresh";
  if (status === "role_changed") return "Your role changed, so we are starting again";
  if (shown <= 0) return "Nothing stands out this week";
  return `${COUNT_WORD[Math.min(shown, 3)]} ${shown === 1 ? "thing" : "things"} from your week`;
}

/** What to say under the title when there are no pointers, when the engine sent no message of its own. Fixed words. */
export function quietBody(status: string): string {
  if (status === "onboarding") return "It needs a few more days of your normal work before it can say anything useful. You do not have to do anything extra.";
  if (status === "no_data") return "No steps from your role have been counted yet. Nothing was lost; there is simply nothing to compare.";
  if (status === "stale") return `Some of the sources are out of date, so ${APP_NAME} is saying nothing rather than something old.`;
  if (status === "role_changed") return "Pointers start again for a new role, so you are not compared with your old one.";
  return "That is a normal result: none of your numbers moved far enough to be worth your time.";
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const parts = (iso: string): [number, number] | null => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? [Number(m[3]), Number(m[2]) - 1] : null;
};

/** "9 to 15 November", or "30 November to 6 December" when the week crosses a month. Null when the dates cannot be read. */
export function weekLabel(week: WireWorker["week"]): string | null {
  if (!week) return null;
  const a = parts(week.from), b = parts(week.to);
  if (!a || !b) return null;
  return a[1] === b[1] ? `${a[0]} to ${b[0]} ${MONTHS[b[1]]}` : `${a[0]} ${MONTHS[a[1]]} to ${b[0]} ${MONTHS[b[1]]}`;
}

export interface RepeatsTotal { actions: number; hours_per_week: { point: number; lo: number; hi: number } }

/** "6 repeated actions, about 3.4 hours a week" and the interval for the hint. Null when the total is missing or empty. Under an hour it speaks in minutes. */
export function repeatsLine(t: RepeatsTotal | null | undefined): { line: string; hint: string } | null {
  if (!t || t.actions <= 0) return null;
  const hrs = t.hours_per_week.point;
  const minutes = hrs < 1;
  const f = (h: number): string => (minutes ? String(Math.max(1, Math.round(h * 60))) : String(Math.round(h * 10) / 10));
  const unit = minutes ? "minutes" : f(hrs) === "1" ? "hour" : "hours";
  return {
    line: `${t.actions} repeated ${t.actions === 1 ? "action" : "actions"}, about ${f(hrs)} ${unit} a week`,
    hint: `A 95% interval: ${f(t.hours_per_week.lo)} to ${f(t.hours_per_week.hi)} ${minutes ? "minutes" : "hours"} a week. Counted from your own repeated steps, not from other people.`,
  };
}
