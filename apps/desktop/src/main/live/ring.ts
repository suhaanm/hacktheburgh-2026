// The voice ring, drawn through the overlay controller's public contract (nothing in overlay/** is touched). One annotation, replaced in
// place; its id starts with "point-" so the controller treats it as temporary guidance that the next ring supersedes. No label and no note:
// the ring never shows words the model wrote.
import type { OverlayController } from '../../shared/contracts'
import type { RingPort } from './ports'

export const VOICE_RING_ID = 'point-voice'
export const VOICE_GHOST_ID = 'point-voice-ghost'

export function createRingPort(overlay: Pick<OverlayController, 'show' | 'clear'>): RingPort {
  let ghostShown = false
  return {
    show(box, opts) {
      const [y0, x0, y1, x1] = box
      const ring = { id: VOICE_RING_ID, kind: 'ring' as const, tone: 'guide' as const, box: { xmin: x0, ymin: y0, xmax: x1, ymax: y1 }, exact: true }
      // The ghost cursor flies in from where the worker's own pointer is and stops at the centre of the box. No press: pointing is not clicking.
      ghostShown = opts?.ghost === true
      if (opts?.ghost) overlay.show([ring, { id: VOICE_GHOST_ID, kind: 'ghostCursor', tone: 'guide', path: [{ x: (x0 + x1) / 2, y: (y0 + y1) / 2 }] }])
      else overlay.show([ring])
    },
    clear() {
      overlay.clear(ghostShown ? [VOICE_RING_ID, VOICE_GHOST_ID] : [VOICE_RING_ID])
      ghostShown = false
    },
  }
}
