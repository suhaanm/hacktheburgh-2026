// Files that still carry one of the two words owner decision D57 removed (8 Nov 2026: "remove the word and every tag, badge, chip and label that used it from
// the app, fully") in something a person can read or hear, listed on 8 Nov at about 00:50 UTC. Each entry names the track that owns the file. The wording track
// (W) cleaned the shared parts: components/common, lib, the fixtures, the engine and agent text, the eval report, and the desktop renderer. The notes below do
// not repeat the two words, so this file is itself clean.
//
// It is a ratchet, not an allow-list: a file that is not listed must have no finding; a listed file must still have one (so its line is deleted the moment its
// track lands: the test names the stale line); and the list can only get shorter. It must be EMPTY by 05:00 on 8 Nov. Read by copy-lint.test.ts and
// words.test.ts; KNACK_LINT_STRICT=1 ignores it in both and shows every finding.
export const PENDING_D57: Record<string, string> = {
  // Track B (Home, shell, first run, sidebar)
  "apps/dashboard/src/components/home/noticesData.ts": "Track B: the example-data notice still carries a parenthetical tag",
  "apps/dashboard/src/screens/Home/Home.tsx": "Track B: the example-week line still names the old kind of firm",
  // Track C (Needs you, Routines, Your data, Settings, Agents)
};
export const PENDING_D57_MAX = 2;
