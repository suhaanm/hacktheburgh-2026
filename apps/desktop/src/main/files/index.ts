// Public surface of the files feature (FILES lane). `createFiles` builds the service for the DI bag in src/main/services.ts.
import os from 'node:os'
import type { FilesService } from '../../shared/files'
import type { GeminiDeps } from '../gemini/client'
import { createEmbedderFromEnv } from './embed'
import { createGeminiExtractor } from './extract'
import { createFilesService, type FilesCtx } from './service'

export { registerFilesIpc } from './ipc'
export { createFilesService } from './service'
export { checkFolder } from './consent'

// `gemini` null (ALONGSIDE_MOCK) keeps everything local: no embeddings, no PDF/image reading, keyword search only.
export function createFiles(ctx: FilesCtx, gemini: GeminiDeps | null): FilesService {
  return createFilesService({
    ctx,
    home: os.homedir(),
    embedder: gemini ? createEmbedderFromEnv(ctx.log) : null,
    extractor: gemini ? createGeminiExtractor(gemini) : null,
    autoStart: true,
  })
}
