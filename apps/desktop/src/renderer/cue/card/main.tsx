import { useEffect, useState, type ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import '../../design/overlay-fonts.css'
import './cue.css'
import type { CueView } from '../../../main/cue/ipc'
import { CUE_TOKENS } from '../../../main/cue/tokens'
import { CuePanel } from './CuePanel'

const root = document.documentElement.style
root.setProperty('--cue-card-w', `${CUE_TOKENS.card.width}px`)
root.setProperty('--cue-chip-max', `${CUE_TOKENS.chip.maxWidth}px`)
root.setProperty('--dur-out', `${CUE_TOKENS.timing.crossfadeMs}ms`)

function App(): ReactElement {
  const [view, setView] = useState<CueView>(null)
  useEffect(() => {
    const api = window.understudyCue
    if (!api) return
    let alive = true
    const off = api.onView((v) => alive && setView(v))
    void api.get().then((v) => alive && setView(v)).catch(() => undefined) // main pushes the view too
    return () => {
      alive = false
      off()
    }
  }, [])
  return <CuePanel view={view} onAction={(a) => window.understudyCue?.action(a)} onSize={(s) => window.understudyCue?.size(s)} />
}

createRoot(document.getElementById('root') as HTMLElement).render(<App />)
