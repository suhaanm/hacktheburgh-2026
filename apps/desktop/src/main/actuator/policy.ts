// What "do it for me" will never click. Matched case-insensitively against the grounded label and the target text.
// Prefix matches on purpose ("pay" also catches "payment"): a false refusal only means the assistant shows instead.
const DENY = [
  'pay',
  'purchase',
  'buy',
  'order',
  'check[\\s-]*out',
  'send',
  'submit',
  'delete',
  'remove',
  'erase',
  'transfer',
  'confirm',
  'sign[\\s-]*in',
  'log[\\s-]*in',
  'password',
  'card',
  'allow',
  'grant',
  'install',
  'accept',
  // Consent / cookie choices are the person's own: never clicked for them (the label scan stays strict).
  'agree',
  'i\\s+agree',
  'consent',
  'cookie',
  'allow\\s+all',
  'accept\\s+all',
]

const DENY_RE = new RegExp(`(?:^|[^a-z0-9])(?:${DENY.join('|')})`, 'i')

// The first denied word found in any of the texts, or null.
export function denylistMatch(...texts: (string | undefined)[]): string | null {
  for (const text of texts) {
    if (!text) continue
    const m = DENY_RE.exec(text)
    if (m) return m[0].replace(/^[^a-z0-9]/i, '').toLowerCase()
  }
  return null
}
