import { createRoot } from 'react-dom/client'
import '../design/fonts'
import { Overlay } from './Overlay'

createRoot(document.getElementById('root') as HTMLElement).render(<Overlay />)
