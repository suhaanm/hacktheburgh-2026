// Owner decision D57 and its clarification (8 Nov 2026): no chip, pill or label on the Firm screens says the firm or its names were generated. There was a
// FirmBadge and a note at the top of every view; both are gone. Where the numbers come from is one plain sentence inside the closed "About this data".

/** "22 people", "1 approval": the unit agrees with the number. */
export function nWord(n: number, unit: string): string {
  const one: Record<string, string> = { people: "person", approvals: "approval", occurrences: "occurrence", pointers: "pointer", runs: "run", users: "user" };
  return `${n.toLocaleString("en-GB")} ${n === 1 ? one[unit] ?? unit.replace(/s$/, "") : unit}`;
}
