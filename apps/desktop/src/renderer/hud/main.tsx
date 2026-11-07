import { createRoot } from 'react-dom/client'
import '../design/overlay-fonts.css'
import './hud.css'
import { HudApp } from './HudApp'

createRoot(document.getElementById('root') as HTMLElement).render(<HudApp />)
