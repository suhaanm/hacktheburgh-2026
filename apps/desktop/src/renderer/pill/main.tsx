import { createRoot } from 'react-dom/client'
import '../design/overlay-fonts.css'
import './pill.css'
import { PillApp } from './PillApp'

createRoot(document.getElementById('root') as HTMLElement).render(<PillApp />)
