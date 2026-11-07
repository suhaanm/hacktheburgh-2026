import { createRoot } from 'react-dom/client'
import { followSystemTheme } from '../design'
import '../design/styles'
import { App } from './App'
import { startLiveBridge } from '../live'
import { startController } from './controller'
import { startShowtimeCues } from './showtime-cues'

document.body.classList.add('al-app')
followSystemTheme()
startController()
startLiveBridge() // the microphone and the speaker, only when main asks (a no-op unless the preload exposes window.understudyLive)
startShowtimeCues() // DEMO: narration audio + view cues from the scripted walkthrough
createRoot(document.getElementById('root') as HTMLElement).render(<App />)
