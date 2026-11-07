// Registers app://knack with Electron. The scheme must be declared before the app is ready; the handler is attached to the default session afterwards.
import { protocol, session } from 'electron'
import { APP_SCHEME } from '../../shared/brand'
import { createAppHandler, type AppProtocolDeps } from './app-protocol'

/** Call at module load, before app.whenReady(): marks app:// as a standard, secure scheme (so localStorage, fetch and relative URLs behave like https). */
export function registerAppScheme(): void {
  protocol.registerSchemesAsPrivileged([{ scheme: APP_SCHEME, privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } }])
}

/** After ready: serve app:// from the dashboard build, forward /engine and /agent to the local services, with the policy on every response. */
export function registerAppProtocol(deps: AppProtocolDeps): () => void {
  const target = session.defaultSession
  target.protocol.handle(APP_SCHEME, createAppHandler(deps))
  return () => target.protocol.unhandle(APP_SCHEME)
}
