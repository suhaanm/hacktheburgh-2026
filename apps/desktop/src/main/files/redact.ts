// What never gets indexed: long digit runs (card, account, phone numbers), anything on a password/passcode/PIN line,
// and long token-like strings. Redaction happens BEFORE chunking, so nothing sensitive reaches the embedding API or disk.

// Bump when redaction gets stricter: an index built with an older version is dropped on load and rebuilt.
export const REDACT_VERSION = 2

const SECRET_LINE = /\b(pass(?:word|code|phrase)s?|pin)\b/i
// Bank details: any line that names them is dropped whole.
const BANK_LINE = /\b(account\s*(?:number|no\.?|num|#)|sort\s*-?\s*code|iban|swift|bic)\b/i
// Sort code (12-34-56), IBAN (GB82 WEST 1234 5698 7654 32) and a bare 8-digit UK account number.
const SORT_CODE = /\b\d{2}-\d{2}-\d{2}\b/g
const IBAN = /\b[A-Za-z]{2}\d{2}(?: ?[A-Za-z0-9]{4}){2,7}(?: ?[A-Za-z0-9]{1,4})?\b/g
const EIGHT_DIGITS = /(?<![\d.,-])\d{8}(?![\d.,-]|\d)/g
// 9 or more digits, allowing single spaces or dashes between them (1234 5678 9012 3456, 07700 900123).
const LONG_DIGITS = /\d(?:[ -]?\d){8,}/g
const TOKENISH = /\b(?:AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|[A-Za-z0-9+/_-]{40,}={0,2})\b/g

export function redactForIndex(text: string): string {
  return text
    .split('\n')
    .map((line) =>
      SECRET_LINE.test(line) || BANK_LINE.test(line)
        ? '[removed]'
        : line
            .replace(TOKENISH, '[token removed]')
            .replace(IBAN, (m) => (/\d/.test(m.slice(2, 4)) && /\d{4}/.test(m) ? '[number removed]' : m))
            .replace(LONG_DIGITS, '[number removed]')
            .replace(SORT_CODE, '[number removed]')
            .replace(EIGHT_DIGITS, '[number removed]'),
    )
    .join('\n')
}
