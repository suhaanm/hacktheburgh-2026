// What an annotation note says on the screen: one short line. The full sentence stays with the decision (the dashboard's "Why this?").
// Pure, so it is tested without a DOM.

const CONNECTIVE = /\s+(?:before|after|because|so that|while|when|until|and then)\s+/i

/** At most `max` characters, cut where a thought ends: the action before its reason, else the first sentence, else a word boundary. */
export function compactNote(text: string, max = 40): string {
  const t = text.replace(/\s+/g, ' ').trim()
  if (t === '') return ''
  const plain = (s: string): string => s.replace(/[\s.,;:]+$/, '')
  if (plain(t).length <= max) return plain(t)
  const head = plain(t.split(CONNECTIVE)[0] ?? t)
  if (head.length >= 6 && head.length <= max) return head
  const sentence = plain(t.split(/(?<=[.?!])\s/)[0] ?? t)
  if (sentence.length <= max) return sentence
  const room = t.slice(0, max - 1)
  const space = room.lastIndexOf(' ')
  return `${plain(space >= 12 ? room.slice(0, space) : room)}…`
}
