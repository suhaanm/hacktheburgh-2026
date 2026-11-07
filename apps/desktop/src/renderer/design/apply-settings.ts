import { PERSONAS } from '../../shared/personas'
import type { PersonaId } from '../../shared/protocol'
import type { Settings } from '../../shared/settings'

export type DesignSettings = Pick<Settings, 'bigAnnotations' | 'highContrast' | 'dyslexiaFont'> &
  Partial<Pick<Settings, 'theme' | 'glass' | 'glassOpacity' | 'textScale'>>

const ACCENT_VARS = ['--accent', '--accent-soft', '--on-accent'] as const

/** Text-bearing shell areas never fall below this, and cards never below CARD_FLOOR, so glass stays readable. */
export const GLASS_SHELL_FLOOR = 0.7
export const GLASS_CARD_FLOOR = 0.94

export function glassAlphas(opacity: number): { shell: number; card: number } {
  const o = Math.min(1, Math.max(0.35, opacity))
  return { shell: GLASS_SHELL_FLOOR + (1 - GLASS_SHELL_FLOOR) * ((o - 0.35) / 0.65), card: Math.max(GLASS_CARD_FLOOR, o) }
}

const osPrefersDark = (): boolean => window.matchMedia('(prefers-color-scheme: dark)').matches
const glassSupported = (): boolean => /Mac/i.test(navigator.platform || navigator.userAgent) && !window.matchMedia('(prefers-reduced-transparency: reduce)').matches

/**
 * Mirrors the look-and-feel settings and the persona accent onto <html>, where tokens.css reads them.
 * Glass needs the window to be transparent (macOS vibrancy); elsewhere, and under high contrast, it stays solid.
 */
export function applyDesignSettings(settings: DesignSettings, persona: PersonaId | null, root: HTMLElement = document.documentElement, opts: { glassSupported?: boolean } = {}): void {
  root.dataset.bigAnnotations = String(settings.bigAnnotations)
  root.dataset.highContrast = String(settings.highContrast)
  root.dataset.dyslexiaFont = String(settings.dyslexiaFont)

  const theme = settings.theme ?? 'system'
  root.dataset.themeSetting = theme
  root.dataset.theme = theme === 'system' ? (osPrefersDark() ? 'dark' : 'light') : theme

  const glass = (settings.glass ?? true) && !settings.highContrast && (opts.glassSupported ?? glassSupported())
  root.dataset.glass = String(glass)
  const { shell, card } = glassAlphas(settings.glassOpacity ?? 0.78)
  root.style.setProperty('--glass-shell', `${(shell * 100).toFixed(1)}%`)
  root.style.setProperty('--glass-card', `${(card * 100).toFixed(1)}%`)
  root.style.setProperty('--ui-scale', String(Math.min(1.5, Math.max(0.9, settings.textScale ?? 1))))

  if (persona) {
    const token = PERSONAS[persona].accentToken
    root.dataset.persona = persona
    root.style.setProperty('--accent', `var(--${token})`)
    root.style.setProperty('--accent-soft', `var(--${token}-soft)`)
    root.style.setProperty('--on-accent', `var(--on-${token})`)
  } else {
    delete root.dataset.persona
    for (const name of ACCENT_VARS) root.style.removeProperty(name)
  }
}

/** Keeps data-theme in step with the operating system while the setting is 'system'. Returns an unsubscribe function. */
export function followSystemTheme(root: HTMLElement = document.documentElement): () => void {
  const query = window.matchMedia('(prefers-color-scheme: dark)')
  const apply = (): void => {
    if ((root.dataset.themeSetting ?? 'system') === 'system') root.dataset.theme = query.matches ? 'dark' : 'light'
  }
  apply()
  query.addEventListener('change', apply)
  return () => query.removeEventListener('change', apply)
}
