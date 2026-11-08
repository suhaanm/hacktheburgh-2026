// "About this screen" (Cmd-slash, or the palette's "Explain this screen"): what the screen is and where its numbers come from, in fixed words.
// This is where the explanation that used to sit in ledes and notes now lives (docs/KNACK_UX.md section 5). It never replaces a printed fact:
// the origin badge, consent text, limits and consequences stay on the screen itself. Pure data, so the copy rules are tests.
import type { Screen } from "../../router";
import type { GrowthSection } from "../home/navModel";

export interface About { what: string; from: string; limit?: string }

export const ABOUT: Record<Screen, About> = {
  home: {
    what: "One sentence about your week and one thing you can do about it.",
    from: "Your own steps this week against the weeks before, and against the role's experts. The pointer is chosen by fixed rules, not by a model.",
    limit: "It says nothing rather than something old.",
  },
  "needs-you": {
    what: "Everything that waits on you: approvals, paused runs, routine suggestions and prepared actions.",
    from: "Runs and routines on this laptop. Nothing here is decided for you; an approval is always a click.",
  },
  routines: {
    what: "What runs for you, how far it is trusted, and what could run next.",
    from: "Your approved routines, and steps you repeat that could become one. Hours saved are estimates with an interval.",
    limit: "Nothing runs until you say so, one routine at a time.",
  },
  growth: {
    what: "Whether you need less help over time.",
    from: "Each step of your role you finish, and how much help it took. Counted on this laptop.",
    limit: "It measures help needed, not expertise, and it is not for evaluating individuals.",
  },
  "your-data": {
    what: "What Knack remembers, measures and has sent, with a way to delete each part.",
    from: "The memory file, the counts and the record of calls, all stored on this laptop and owned by you.",
    limit: "Every call from Knack is listed, but it cannot show what other software on this computer does.",
  },
  firm: {
    what: "Where the firm loses time and what changed.",
    from: "Counts and durations for the whole firm, never names, titles or content. Example data uses a made-up firm.",
    limit: "For coaching and onboarding, not for evaluating individuals.",
  },
  brief: {
    what: "A one-page summary of the firm, ready to print.",
    from: "The same counts as the Firm view, as bands and counts. No names, no titles, no content.",
    limit: "For coaching and onboarding, not for evaluating individuals.",
  },
  forecasts: {
    what: "What to expect, and what to do about it, with how well past forecasts held up behind a disclosure.",
    from: "Forecasts checked against what happened, with calibration scores.",
    limit: "A forecast is a probability, not a promise.",
  },
  roles: {
    what: "Experts and juniors side by side, one row per role.",
    from: "Finished-without-help rates on one scale, with the number of people behind each.",
    limit: "A role with no expert is not compared.",
  },
  people: {
    what: "Everyone, grouped by role, as bands and counts.",
    from: "Counts and durations. A person's own detail shows only when that person agreed.",
    limit: "For coaching and onboarding, not for evaluating individuals.",
  },
  onboarding: {
    what: "How fast new people reach independence.",
    from: "Each role's curve of steps to reach the target, with its interval and the number of people.",
  },
  automation: {
    what: "Repeated work across the firm, as hours a week that could run for people.",
    from: "Actions that several people repeat, counted and never named. A row needs at least five people.",
    limit: "Hours are estimates with an interval.",
  },
  risk: {
    what: "Approvals, safety pauses, and how much data the picture rests on.",
    from: "Counts from every run in the firm. Nothing is read from anyone's screen.",
  },
  agents: {
    what: "Helpers that work while someone does something else, and what each may use.",
    from: "Runs started on this laptop, each with a budget and a lease that can be revoked.",
  },
  models: {
    what: "Which model answers, how fast, and what it costs.",
    from: "Calls made for steps people allowed, listed in Your data. Costs are counted against the spending cap.",
  },
  today: {
    what: "The step you are on, how much help Knack gives, and why it said what it said.",
    from: "The live coach reading your task step by step. Help fades as you need less.",
    limit: "It reads steps, not people, and says nothing in study mode.",
  },
  evidence: {
    what: "How every number in Knack was checked, for reviewers.",
    from: "Held-out tests, calibration, limits and the privacy checks, printed whole.",
    limit: "Study results are from four people and are not a claim that novices become experts.",
  },
  "first-run": {
    what: "A short start: your role, what Knack may do, and a check that it works.",
    from: "Your answers write the memory file on this laptop. Everything else takes the role's safe defaults, and nothing is on until you click Yes.",
  },
  setup: {
    what: "The set-up questions again, one at a time.",
    from: "Your role's pack. Answers rewrite lines in the memory file.",
  },
};

/** Growth is one page with five sections; the panel explains the one on screen. */
export const ABOUT_GROWTH: Record<Exclude<GrowthSection, "progress">, About> = {
  time: {
    what: "Where your time goes in a week: when you are at work, and the shape of your calendar against an experienced worker's.",
    from: "Times only: when you were active, and counts and durations of meetings and blocks. No titles, names or invites are read or kept.",
    limit: "Suggestions send, book and change nothing.",
  },
  steps: {
    what: "Where your time goes, step by step, against one experienced worker's way of doing the task.",
    from: "Durations of your steps and of the experienced worker's steps for the same task, with intervals.",
    limit: "A gap is where to look, not a verdict.",
  },
  map: {
    what: "How your routines, skills and notes connect.",
    from: "The routines you approved, the skills Knack tracks and the lines in your memory file.",
  },
  commits: {
    what: "How you commit, against an experienced programmer.",
    from: "Counts and sizes of commits from your own repositories, never code or messages.",
  },
};

/** The text for a screen, and for the Growth section when the screen is Growth. */
export const aboutFor = (id: Screen, section: GrowthSection | null = null): About => (id === "growth" && section && section !== "progress" ? ABOUT_GROWTH[section] : ABOUT[id]);

export const wordsOf = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;
