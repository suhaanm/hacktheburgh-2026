// Menu-bar (tray) -> dock window commands. The dock renderer owns what it shows; main only asks.

export type DockView = 'chat' | 'onboarding' | 'permissions' | 'settings'

export type ShellCommand =
  | { type: 'expand' }
  | { type: 'collapse' }
  | { type: 'toggle' }
  // Expand the panel and switch to this view. 'chat' means "type instead of talking" (text mode).
  | { type: 'view'; view: DockView }
