import { describe, expect, it } from 'vitest'
import type { FilesStatus } from '../../../shared/files'
import { describeStatus } from './describe'

const base: FilesStatus = { enabled: true, folders: [{ path: '/a', name: 'a', fileCount: 3 }], indexing: false, done: 0, total: 0, indexedFiles: 3, chunks: 5, lastIndexedAt: 1, skippedFiles: 0, truncated: false, mode: 'semantic', embedModel: 'm' }

describe('describeStatus', () => {
  it('is quiet when off and guides when there is no folder', () => {
    expect(describeStatus({ ...base, enabled: false })).toBe('')
    expect(describeStatus({ ...base, folders: [] })).toBe('Add a folder to begin.')
  })
  it('shows progress, counts and the words-only note', () => {
    expect(describeStatus({ ...base, indexing: true, done: 1, total: 4 })).toContain('1 of 4')
    expect(describeStatus(base)).toBe('I can look at 3 files.')
    expect(describeStatus({ ...base, indexedFiles: 1, mode: 'keyword' })).toContain('words only')
  })
})
