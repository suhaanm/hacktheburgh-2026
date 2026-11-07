import type { FilesStatus } from '../../../shared/files'

// One plain-English line for the "Files I can look at" section.
export function describeStatus(s: FilesStatus): string {
  if (!s.enabled) return ''
  if (s.folders.length === 0) return 'Add a folder to begin.'
  if (s.indexing) return s.total > 0 ? `Reading your files: ${s.done} of ${s.total}...` : 'Getting ready to read your files...'
  if (s.lastError) return s.lastError
  const files = `${s.indexedFiles} ${s.indexedFiles === 1 ? 'file' : 'files'}`
  const how = s.mode === 'keyword' ? ' Searching by words only for now.' : ''
  const cap = s.truncated ? ' That is as many as I can look at.' : ''
  return `I can look at ${files}.${how}${cap}`
}
