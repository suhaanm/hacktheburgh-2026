// What the Cue panel page may ask of main, validated again here because the page is a renderer: the sender is checked by the window code, the
// shape and the ids by this. Anything else is dropped.
import { z } from 'zod'

const id = z.string().regex(/^[A-Za-z0-9_.:-]{1,80}$/)

export const CueCardActionSchema = z.discriminatedUnion('type', [
  z.strictObject({ type: z.literal('answer'), id }),
  z.strictObject({ type: z.literal('other') }),
  z.strictObject({ type: z.literal('dismiss') }),
  z.strictObject({ type: z.literal('why'), open: z.boolean() }),
  z.strictObject({ type: z.literal('show_me') }),
  z.strictObject({ type: z.literal('know_this') }),
  z.strictObject({ type: z.literal('offer'), yes: z.boolean() }),
  z.strictObject({ type: z.literal('touch') }),
])

export const CueSizeSchema = z.strictObject({ w: z.number().int().min(1).max(1200), h: z.number().int().min(1).max(1200) })
