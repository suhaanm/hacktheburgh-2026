import { createRoot } from 'react-dom/client'
import { followSystemTheme } from '../design'
import '../design/styles'
import './toast.css'
import { ToastApp } from './ToastApp'

document.body.classList.add('al-app')
followSystemTheme()
createRoot(document.getElementById('root') as HTMLElement).render(<ToastApp />)
