import { createRoot } from 'react-dom/client'
import './hud.css'
import { HudApp } from './HudApp'

createRoot(document.getElementById('root') as HTMLElement).render(<HudApp />)
