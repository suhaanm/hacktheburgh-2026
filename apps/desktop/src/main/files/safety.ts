// Snippets are the person's own file text, shown to a model: treat as untrusted data.
// This cleans them (no hidden characters, no look-alike agent markers) and flags text that reads like instructions to an AI.
import { FILES_LIMITS } from '../../shared/files'

// eslint-disable-next-line no-control-regex
const INVISIBLE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F​-‏‪-‮⁠-⁤﻿]/g

const INJECTION: RegExp[] = [
  /\b(ignore|disregard|forget|override)\b[^.\n]{0,25}\b(previous|prior|above|earlier|all|any|your)\b[^.\n]{0,25}\b(instructions?|prompts?|rules?|messages?)\b/i,
  /\byou are now (a|an|in|the)\b/i,
  /\b(system|developer) (prompt|message|instructions?)\b/i,
  /\b(reveal|print|repeat|show|output)\b[^.\n]{0,12}\b(your|the) (system |hidden |initial )?(prompt|instructions?)\b/i,
  /\b(tell|instruct|command|ask) the (user|assistant|ai|chatbot|model)\b/i,
  /\bnew instructions?\s*:/i,
  /\b(call|use|run|invoke) the [a-z_]+ (tool|function)\b/i,
]

export function looksLikeInjection(text: string): boolean {
  return INJECTION.some((re) => re.test(text))
}

export function cleanSnippet(text: string, max: number = FILES_LIMITS.snippetChars): string {
  const flat = text
    .replace(INVISIBLE, '')
    .replace(/\[/g, '(')
    .replace(/\]/g, ')')
    .replace(/\s*\n+\s*/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .trim()
  if (flat.length <= max) return flat
  const cut = flat.slice(0, max - 1)
  const lastSpace = cut.lastIndexOf(' ')
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`
}
