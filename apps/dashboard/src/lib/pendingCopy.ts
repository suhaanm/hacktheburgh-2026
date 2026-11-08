// Files that still carry one of the words owner decision D57 removed (8 Nov 2026: "remove the word and every tag, badge, chip and label that used it from
// the app, fully"; clarified the same night: no tag or label of ANY wording says the data was generated or made up) in something a person can read or hear.
// Each entry names the track that owns the file. The wording track (W) cleaned the shared parts: components/common, lib, the fixtures, the engine and agent
// text, the eval report, the desktop renderer, Home's origin chip, the Firm head note and badge. The notes below do not repeat the words, so this file is
// itself clean.
//
// It is a ratchet, not an allow-list: a file that is not listed must have no finding; a listed file must still have one (so its line is deleted the moment its
// track lands: the test names the stale line); and the list can only get shorter. It must be EMPTY by 05:00 on 8 Nov. Read by copy-lint.test.ts and
// words.test.ts; KNACK_LINT_STRICT=1 ignores it in both and shows every finding.
export const PENDING_D57: Record<string, string> = {
  // Track D (Growth, Genome, Firm, Roles, Onboarding, Today, Models, Presence, Graph, Week, Git, Forecasts, Evidence head)
  "apps/dashboard/src/components/firm/ScorecardPanel.tsx": "Track D: two scorecard sentences",
  "apps/dashboard/src/components/firm/scorecard.ts": "Track D: the leave-one-person-out sentence",
  "apps/dashboard/src/components/growth/model.ts": "Track D: the origin sentences and the experimental-score caveats",
  "apps/dashboard/src/screens/Evidence.tsx": "Track D: the head's lede",
};
export const PENDING_D57_MAX = 4;
