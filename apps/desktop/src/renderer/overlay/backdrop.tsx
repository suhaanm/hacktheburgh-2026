// Mock desktop used only by the render harness (demo.html). Light and dark variants so every annotation is
// checked for legibility on both. Layout comes from MOCK in fixtures.ts (norm 0-1000) so rings land on real buttons.
import type { CSSProperties, ReactElement } from 'react'
import type { NormBox } from '../../shared/protocol'
import { MOCK } from './fixtures'

const pos = (b: NormBox): CSSProperties => ({ position: 'absolute', left: `${b.xmin / 10}%`, top: `${b.ymin / 10}%`, width: `${(b.xmax - b.xmin) / 10}%`, height: `${(b.ymax - b.ymin) / 10}%` })

export function Backdrop({ mode }: { mode: 'light' | 'dark' }): ReactElement {
  const dark = mode === 'dark'
  const c = dark
    ? { wall: 'linear-gradient(135deg,#101a33,#2a1b47 60%,#0b2a3a)', win: '#1d2230', bar: '#2a3042', ink: '#e8ecf5', sub: '#9aa3ba', tile: 'linear-gradient(160deg,#2b3a5a,#1a2236)', btn: '#323a52', msg: '#262d40', menu: 'rgba(20,24,38,.9)' }
    : { wall: 'linear-gradient(135deg,#cfe3f5,#f1e6d3 60%,#dfeee6)', win: '#ffffff', bar: '#e9ecf2', ink: '#1c2230', sub: '#566074', tile: 'linear-gradient(160deg,#c6d6ee,#e8eef8)', btn: '#e4e8f1', msg: '#eef1f7', menu: 'rgba(245,247,252,.92)' }
  const btn = (b: NormBox, label: string, extra: CSSProperties = {}): ReactElement => (
    <div key={label} style={{ ...pos(b), background: c.btn, color: c.ink, borderRadius: 999, display: 'grid', placeItems: 'center', fontSize: 13, fontFamily: 'system-ui', ...extra }}>
      {label}
    </div>
  )
  return (
    <div style={{ position: 'absolute', inset: 0, background: c.wall, fontFamily: 'system-ui, sans-serif', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, right: 0, height: 33, zIndex: 0, background: c.menu, color: c.ink, fontSize: 14, display: 'flex', alignItems: 'center', gap: 18, padding: '0 14px' }}>
        <b>Files</b>
        <span>Edit</span>
        <span>View</span>
        <span style={{ marginLeft: 'auto' }}>Sat 14:05</span>
      </div>
      <div style={{ ...pos(MOCK.videoWindow), background: c.win, borderRadius: 14, boxShadow: '0 12px 40px rgba(0,0,0,.35)', overflow: 'hidden' }}>
        <div style={{ height: 40, background: c.bar, color: c.ink, fontSize: 14, display: 'flex', alignItems: 'center', padding: '0 14px', gap: 8 }}>
          <i style={{ width: 11, height: 11, borderRadius: 9, background: '#ff5f57' }} />
          <i style={{ width: 11, height: 11, borderRadius: 9, background: '#febc2e' }} />
          <i style={{ width: 11, height: 11, borderRadius: 9, background: '#28c840' }} />
          <span style={{ marginLeft: 12 }}>Video call - Sam</span>
        </div>
      </div>
      <div style={{ ...pos(MOCK.videoTile), background: c.tile, borderRadius: 12, display: 'grid', placeItems: 'center' }}>
        <div style={{ width: 120, height: 120, borderRadius: 120, background: dark ? '#4b5b86' : '#8da3d4', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 44 }}>S</div>
      </div>
      {btn(MOCK.mic, 'Mic')}
      {btn(MOCK.camera, 'Cam')}
      {btn(MOCK.share, 'Share')}
      {btn(MOCK.chat, 'Chat')}
      {btn(MOCK.hangUp, 'Hang up', { background: '#d6453a', color: '#fff', fontWeight: 700 })}
      <div style={{ ...pos(MOCK.messagesWindow), background: c.win, borderRadius: 14, boxShadow: '0 12px 40px rgba(0,0,0,.35)', overflow: 'hidden' }}>
        <div style={{ height: 40, background: c.bar, color: c.ink, fontSize: 14, display: 'flex', alignItems: 'center', padding: '0 14px' }}>Messages</div>
      </div>
      <div style={{ ...pos(MOCK.scamBubble), background: c.msg, borderRadius: 14, color: c.ink, fontSize: 15, lineHeight: 1.45, padding: 0 }}>
        <div style={{ ...pos(MOCK.scamLine1), left: '0.6%', fontSize: 15 }} />
      </div>
      <div style={{ ...pos(MOCK.scamLine1), color: c.ink, fontSize: 16, display: 'flex', alignItems: 'center' }}>URGENT: your bank account is locked</div>
      <div style={{ ...pos(MOCK.scamLine2), color: c.ink, fontSize: 16, display: 'flex', alignItems: 'center' }}>Confirm your PIN within 1 hour</div>
      <div style={{ ...pos(MOCK.scamLink), color: dark ? '#7fb2ff' : '#1f55c0', fontSize: 16, textDecoration: 'underline', display: 'flex', alignItems: 'center' }}>http://secure-bank-check.example</div>
      <div style={{ ...pos(box(705, 270, 925, 310)), color: c.sub, fontSize: 13 }}>+44 7700 900123 - Today</div>
      <div style={{ ...pos(MOCK.sendButton), background: dark ? '#3b5bdb' : '#2f6fed', color: '#fff', borderRadius: 10, display: 'grid', placeItems: 'center', fontSize: 14 }}>Send</div>
      <div style={{ ...pos(MOCK.settingsIcon), background: c.menu, color: c.ink, borderRadius: 10, display: 'grid', placeItems: 'center', fontSize: 18 }}>⚙</div>
    </div>
  )
}

function box(xmin: number, ymin: number, xmax: number, ymax: number): NormBox {
  return { xmin, ymin, xmax, ymax }
}
