// Fixed-size chunks (about 800 characters, 100 of overlap) that prefer to break at a paragraph, line or sentence end.
import { FILES_LIMITS } from '../../shared/files'

export interface Chunk {
  text: string
  start: number
}

export const MAX_CHUNKS_PER_FILE = 150

export function normaliseText(text: string): string {
  return text
    .replace(/^﻿/, '')
    .replace(/\r\n?/g, '\n')
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F​-‏‪-‮⁠-⁤﻿]/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/ ?\n ?/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function chunkText(raw: string, size: number = FILES_LIMITS.chunkChars, overlap: number = FILES_LIMITS.chunkOverlap): Chunk[] {
  const text = normaliseText(raw)
  if (text.length === 0) return []
  if (text.length <= size) return text.length >= 12 ? [{ text, start: 0 }] : []
  const chunks: Chunk[] = []
  let start = 0
  while (start < text.length && chunks.length < MAX_CHUNKS_PER_FILE) {
    let end = Math.min(text.length, start + size)
    if (end < text.length) {
      // Look for a natural break in the last quarter of the window.
      const floor = start + Math.floor(size * 0.75)
      const window = text.slice(floor, end)
      const para = window.lastIndexOf('\n\n')
      const line = window.lastIndexOf('\n')
      const sentence = Math.max(window.lastIndexOf('. '), window.lastIndexOf('? '), window.lastIndexOf('! '))
      const space = window.lastIndexOf(' ')
      const rel = [para, line, sentence >= 0 ? sentence + 1 : -1, space].find((i) => i > 0)
      if (rel !== undefined) end = floor + rel + 1
    }
    const piece = text.slice(start, end).trim()
    if (piece.length >= 12) chunks.push({ text: piece, start })
    if (end >= text.length) break
    start = Math.max(end - overlap, start + 1)
  }
  return chunks
}
