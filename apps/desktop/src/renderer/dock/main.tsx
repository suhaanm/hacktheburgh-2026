import { createRoot } from 'react-dom/client'
import { followSystemTheme } from '../design'
import '../design/styles'
import { App } from './App'
import { startController } from './controller'
import { startShowtimeCues } from './showtime-cues'

document.body.classList.add('al-app')
followSystemTheme()
startController()
startShowtimeCues() // DEMO: narration audio + view cues from the scripted walkthrough
createRoot(document.getElementById('root') as HTMLElement).render(<App />)
