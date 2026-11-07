/// <reference types="vite/client" />
// The brand glyph file's text (packages/design/brand/<files.glyph in brand.json>), inlined at build time, for the starting page. Looked up by the name in
// brand.json, so replacing the file or renaming it there is all it takes.
import { BRAND_FILES } from '../../shared/brand'

const files = import.meta.glob('../../../../../packages/design/brand/*.svg', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

export const glyphSvg: string = Object.entries(files).find(([file]) => file.endsWith(`/${BRAND_FILES.glyph}`))?.[1] ?? ''
