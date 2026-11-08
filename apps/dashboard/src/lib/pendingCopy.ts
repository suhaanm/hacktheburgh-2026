// Files that still carry one of the words owner decision D57 removed (8 Nov 2026: "remove the word and every tag, badge, chip and label that used it from
// the app, fully"; clarified the same night: no tag or label of ANY wording says the data was generated or made up) in something a person can read or hear.
// Each entry would name the track that owns the file. IT IS EMPTY: every track has landed (W, B, C, D). Keep the mechanism: a file that is not listed must have
// no finding; a listed file must still have one (the test names a stale line); the list can only get shorter. Read by copy-lint.test.ts and words.test.ts;
// KNACK_LINT_STRICT=1 ignores it in both and shows every finding.
export const PENDING_D57: Record<string, string> = {};
export const PENDING_D57_MAX = 0;

/**
 * The only files that may carry the example family of words (example data, sample data, stand-in, made-up, fixture, and the rest of the list in
 * docs/knack-ux/banned-phrases.json): the Evidence page (admin More) and the report it reads. Its "Measured on" column, limitations and findings state how each
 * evaluation result was obtained, so removing them would make the research claims false (owner, 8 Nov 2026). Every other screen carries none of them.
 */
export const EVIDENCE_PAGE: readonly string[] = [
  "apps/dashboard/src/screens/Evidence.tsx",
  "apps/dashboard/src/components/EvidenceMap.tsx",
  "apps/dashboard/src/components/EvidenceCharts.tsx",
  "apps/dashboard/src/components/HrtEvidence.tsx",
  "apps/dashboard/src/components/LiveRuns.tsx",
  "apps/dashboard/src/lib/evidence.ts",
  "apps/dashboard/src/fixtures/eval-report.json",
];
