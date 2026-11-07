// The voice ring, drawn through the overlay controller's public contract (nothing in overlay/** is touched). One annotation, replaced in
// place; its id starts with "point-" so the controller treats it as temporary guidance that the next ring supersedes. No label and no note:
// the ring never shows words the model wrote.
import type { OverlayController } from '../../shared/contracts'
import type { RingPort } from './ports'

export const VOICE_RING_ID = 'point-voice'

export function createRingPort(overlay: Pick<OverlayController, 'show' | 'clear'>): RingPort {
  return {
    show(box) {
      const [y0, x0, y1, x1] = box
      overlay.show([{ id: VOICE_RING_ID, kind: 'ring', tone: 'guide', box: { xmin: x0, ymin: y0, xmax: x1, ymax: y1 }, exact: true }])
    },
    clear() {
      overlay.clear([VOICE_RING_ID])
    },
  }
}
