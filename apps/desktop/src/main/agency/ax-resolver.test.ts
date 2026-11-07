import { describe, expect, it } from 'vitest'
import { pointsToNorm, normToPoints } from '../actuator/mapping'
import { matchByLabel, parseAxOutput, resolveFromElements, snapToContaining, tokens, type AxElement } from './ax-resolver'

const B = { x: 0, y: 0, width: 1728, height: 1117 }
const ids = ['Delete', 'AllClear', 'Percent', 'Divide', 'Seven', 'Eight', 'Nine', 'Multiply', 'Four', 'Five', 'Six', 'Subtract', 'One', 'Two', 'Three', 'Add', 'Negate', 'Zero', 'Decimal', 'Equals']
const calc: AxElement[] = ids.map((id, i) => ({ role: 'AXButton', title: '', desc: 'button', id, x: 806 + (i % 4) * 54, y: 455 + Math.floor(i / 4) * 54, w: 48, h: 48 }))
calc.push({ role: 'AXButton', title: '', desc: 'close button', id: '', x: 814, y: 340, w: 16, h: 16 })
const by = (id: string) => calc.find((e) => e.id === id) as AxElement

describe('mapping', () => {
  it('pointsToNorm inverts normToPoints on a retina display (points, not pixels)', () => {
    for (const [x, y] of [[0, 0], [830, 479], [1727, 1116], [968 + 24, 671 + 24]]) {
      const back = normToPoints(pointsToNorm({ x, y }, B), B)
      expect(Math.abs(back.x - x)).toBeLessThanOrEqual(1)
      expect(Math.abs(back.y - y)).toBeLessThanOrEqual(1)
    }
  })
  it('honours a display origin', () => {
    const b = { x: -1440, y: 0, width: 1440, height: 900 }
    expect(normToPoints(pointsToNorm({ x: -720, y: 450 }, b), b)).toEqual({ x: -720, y: 450 })
  })
})

describe('tokens', () => {
  it('maps words, symbols and number words to one vocabulary', () => {
    expect(tokens('click the plus button in Calculator')).toEqual(['plus'])
    expect(tokens('click +')).toEqual(['plus'])
    expect(tokens('the = key')).toEqual(['equals'])
    expect(tokens('click the 3 button')).toEqual(['3'])
    expect(tokens('Three', true)).toEqual(['3'])
    expect(tokens('AllClear', true)).toEqual(['all', 'clear'])
    expect(tokens('point at the 3 button')).toEqual(['3'])
  })
})

describe('matchByLabel', () => {
  it.each([
    ['click the 3 button in Calculator', 'Three'],
    ['click the 0 button to continue typing 30', 'Zero'],
    ['click the plus button in Calculator', 'Add'],
    ['the equals (=) button in the Calculator', 'Equals'],
    ['click the multiply button', 'Multiply'],
    ['click the minus sign', 'Subtract'],
    ['click the 1 button', 'One'],
  ])('%s -> %s', (label, id) => {
    expect(matchByLabel(label, calc)?.id).toBe(id)
  })
  it('returns null when nothing matches or the words are generic', () => {
    expect(matchByLabel('click the purple thing', calc)).toBeNull()
    expect(matchByLabel('click the button', calc)).toBeNull()
  })
  it('rejects a namesake far from where vision pointed, accepts the near one', () => {
    const dup = [...calc, { ...by('Three'), id: 'Three', x: 1500, y: 900 }]
    const near = { x: 914 + 24, y: 617 + 24 }
    const m = matchByLabel('click 3', dup, { near })
    expect(m?.x).toBe(914)
    expect(matchByLabel('click 3', [{ ...by('Three'), x: 1500, y: 900 }], { near })).toBeNull()
  })
  it('ambiguous duplicates without a hint are not trusted', () => {
    expect(matchByLabel('click 3', [by('Three'), { ...by('Three'), x: 1000 }])).toBeNull()
  })
})

describe('resolveFromElements', () => {
  it('lands on the exact centre even when vision is 30 points off', () => {
    const vision = pointsToNorm({ x: 914 + 24 + 30, y: 617 + 24 - 10 }, B)
    const r = resolveFromElements('click the 3 button', calc, B, vision)
    expect(r?.how).toBe('label')
    const pt = normToPoints(r!.point, B)
    expect(pt).toEqual({ x: 938, y: 641 })
  })
  it('snaps to the containing control when the words do not match', () => {
    const r = resolveFromElements('click here', calc, B, pointsToNorm({ x: 975, y: 690 }, B))
    expect(r?.how).toBe('snap')
    expect(r?.el.id).toBe('Equals')
  })
  it('returns null with no label match and no containing element', () => {
    expect(resolveFromElements('click here', calc, B, pointsToNorm({ x: 10, y: 10 }, B))).toBeNull()
  })
  it('snapToContaining prefers the smallest frame', () => {
    expect(snapToContaining({ x: 822, y: 348 }, [...calc, { role: 'AXGroup', title: '', desc: '', id: 'big', x: 0, y: 0, w: 2000, h: 2000 }])?.desc).toBe('close button')
  })
})

describe('parseAxOutput', () => {
  it('parses, clips and drops malformed rows', () => {
    const s = parseAxOutput(JSON.stringify({ app: 'Calculator', els: [{ r: 'AXButton', t: '', d: 'x', id: 'One', x: 1, y: 2, w: 3, h: 4 }, { r: 'AXButton', x: 'a' }, null] }))
    expect(s?.els).toHaveLength(1)
    expect(parseAxOutput('nope')).toBeNull()
  })
})
