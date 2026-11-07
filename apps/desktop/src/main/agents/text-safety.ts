// Pure helpers that keep untrusted text (messages, web results, model prose) from steering us
// and keep what we say plain, short and never reassuring about a message's safety.

// Control characters, zero-width characters and bidi overrides are all used to hide instructions.
// eslint-disable-next-line no-control-regex
const INVISIBLE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F​-‏‪-‮⁠-⁤﻿]/g

export function cleanText(input: string, maxLen: number): string {
  const cleaned = input.replace(INVISIBLE, '').replace(/\r\n?/g, '\n').replace(/[ \t]+/g, ' ').trim()
  return cleaned.length > maxLen ? `${cleaned.slice(0, maxLen - 1).trimEnd()}…` : cleaned
}

/** Single line, and no square brackets so text can never imitate our own `[AGENT_RESULT …]` markers. */
export function inlineSafe(input: string, maxLen: number): string {
  return cleanText(input, maxLen * 2).replace(/\s*\n+\s*/g, ' ').replace(/\[/g, '(').replace(/\]/g, ')').slice(0, maxLen).trim()
}

export function splitSentences(text: string): string[] {
  const parts = text.replace(/\s+/g, ' ').match(/[^.!?]+[.!?]*/g) ?? []
  return parts.map((s) => s.trim()).filter((s) => s.length > 0)
}

const REASSURANCE =
  /\b(safe|safely|legit|legitimate|genuine|trustworthy|authentic|reliable|nothing to worry|no need to worry|not a scam|fine to (click|open|reply|trust))\b/i

/** True for any wording that would reassure the user that a message is OK. */
export function soundsReassuring(sentence: string): boolean {
  return REASSURANCE.test(sentence)
}

export function plainSentences(text: string, maxSentences: number, maxCharsEach: number): string[] {
  return splitSentences(inlineSafe(text, 600))
    .filter((s) => !soundsReassuring(s))
    .slice(0, maxSentences)
    .map((s) => inlineSafe(s, maxCharsEach))
}

const SECRET_PATTERNS: [RegExp, string][] = [
  [/\b(?:\d[ -]?){8,}\d\b/g, '[number removed]'],
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '[email removed]'],
  [/\b(password|passcode|pin)\b\s*(is|:|=)\s*\S+/gi, '$1 [removed]'],
]

/** Digit runs, emails and "password is …" never leave this machine in a summary. */
export function redactSensitive(text: string): string {
  return SECRET_PATTERNS.reduce((acc, [pattern, replacement]) => acc.replace(pattern, replacement), text)
}

const INJECTION_PATTERNS: RegExp[] = [
  /\b(ignore|disregard|forget|override)\b[^.\n]{0,20}\b(previous|prior|above|earlier|all|any|your)\b[^.\n]{0,20}\b(instructions?|prompts?|rules?|messages?)\b/i,
  /\byou are now (a|an|in|the)\b[^.\n]{0,40}/i,
  /\b(system|developer) (prompt|message|instructions?)\b/i,
  /\b(reveal|print|repeat|show|output) (me )?(your|the) (system |hidden |initial )?(prompt|instructions?)\b/i,
  /\[\s*(AGENT_RESULT|RUNNER|STALL|SYSTEM|INSTRUCTION)[^\]\n]{0,80}\]?/i,
  /\b(tell|inform|instruct|command) the (user|assistant|ai|chatbot|model)\b[^.\n]{0,60}/i,
  /\bas an? (ai|language model|assistant)\b[^.\n]{0,40}/i,
  /\bnew instructions?\s*:[^.\n]{0,60}/i,
]

export const INJECTION_WHY =
  'This text tries to give orders to a computer assistant. Real messages from people or companies never do that.'

/** Phrases (as they appear in the text) that look aimed at an AI rather than at a person. */
export function findInjectionPhrases(text: string): string[] {
  const found: string[] = []
  for (const pattern of INJECTION_PATTERNS) {
    const match = pattern.exec(text)
    if (!match) continue
    const phrase = inlineSafe(match[0].trim().replace(/[.,;:]+$/, ''), 90)
    if (phrase.length >= 6 && !found.includes(phrase)) found.push(phrase)
  }
  return found
}

export function hostOf(value: string | undefined): string | undefined {
  if (!value) return undefined
  const candidate = value.trim()
  try {
    const host = new URL(/^[a-z]+:\/\//i.test(candidate) ? candidate : `https://${candidate}`).hostname
    return /^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(host) ? host.replace(/^www\./, '').toLowerCase() : undefined
  } catch {
    return undefined
  }
}
