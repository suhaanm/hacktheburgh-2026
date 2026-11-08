// The worker's screens compare the worker with ONE experienced worker, unnamed, never with "the experts" as a group
// (docs/knack-ux/views.md). The engine's own sentences and labels still say "the experts"; this turns them into the worker's words at render time.
// Pure and idempotent: text that already says "an experienced worker" passes through unchanged.

const cap = (match: string, to: string): string => (/^[A-Z]/.test(match) ? to.charAt(0).toUpperCase() + to.slice(1) : to);

export function oneExpert(text: string): string {
  return text
    .replace(/\b(?:the )?reference experts'/gi, (m) => cap(m, "an experienced worker's"))
    .replace(/\bthe experts'/gi, (m) => cap(m, "an experienced worker's"))
    .replace(/\bthe experts\b/gi, (m) => cap(m, "an experienced worker"))
    .replace(/\bexperts'/gi, (m) => cap(m, "an experienced worker's"))
    .replace(/\bexperts\b/gi, (m) => cap(m, "an experienced worker"));
}
