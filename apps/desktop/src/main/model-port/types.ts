// The model port: the ONLY seam through which the desktop app talks to a language model.
//   Providers: `openai` (Responses API over fetch, main process only) and `mock` (scripted, deterministic, no network).
//   Model IDs come from the environment (OPENAI_MODEL_PLANNER / OPENAI_MODEL_FAST / OPENAI_MODEL_COMPUTER_USE) and are never
//   hard-coded. The key (OPENAI_API_KEY) is read in the main process only; nothing here is ever sent to a renderer or logged.
// Services ask for a TIER, not a model: planner = slow and careful, fast = cheap and quick, computer_use = the computer tool.

export type ModelTier = 'planner' | 'fast' | 'computer_use'
export type Effort = 'minimal' | 'low' | 'medium' | 'high'
export type Provider = 'openai' | 'mock'

export interface ModelIds {
  planner: string
  fast: string
  computer_use: string
}

export interface ImageInput {
  jpegBase64: string
  // 'low' costs fewer tokens; 'high' is for reading screens. Default 'high'.
  detail?: 'low' | 'high' | 'auto'
  mime?: 'image/jpeg' | 'image/png'
}

export interface JsonSchemaSpec {
  // A short identifier ([a-zA-Z0-9_-]); some providers require one.
  name: string
  // JSON Schema object. The openai provider makes it strict where it can (see strictify in ./json.ts).
  schema: Record<string, unknown>
}

export interface CompletionRequest {
  // Label for logs, stats and the mock's scripts, e.g. 'grounder.primary'.
  name: string
  tier: ModelTier
  system?: string
  // The user turn. Anything untrusted must already be wrapped as data by the caller.
  text: string
  images?: ImageInput[]
  schema?: JsonSchemaSpec
  effort?: Effort
  // Hosted web search (scam link checks). Ignored by the mock.
  webSearch?: boolean
  // Hard wall-clock budget across all attempts.
  timeoutMs: number
  // Extra attempts after the first for transport-level failures (default 1).
  retries?: number
  maxOutputTokens?: number
}

export interface CompletionResult {
  text: string
  // The concrete model ID that answered (from the environment; the mock reports 'mock').
  model: string
  ms: number
  usage?: { input?: number; output?: number; reasoning?: number }
  // URLs the answer cites (web search only). Empty otherwise.
  citations?: string[]
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export type ComputerAction =
  | { type: 'click'; x: number; y: number; button?: 'left' | 'right' | 'middle' }
  | { type: 'double_click'; x: number; y: number }
  | { type: 'move'; x: number; y: number }
  | { type: 'scroll'; x: number; y: number; scrollX: number; scrollY: number }
  | { type: 'type'; text: string }
  | { type: 'keypress'; keys: string[] }
  | { type: 'wait' }
  | { type: 'drag'; path: Array<{ x: number; y: number }> }
  | { type: 'unknown'; name: string }

export interface ComputerStepRequest {
  goal: string
  // What was already done in this task, from our own code.
  history: readonly string[]
  // A FRESH screenshot. Coordinates in the answer are in the pixel space of this image.
  screenshot: ImageInput & { widthPx: number; heightPx: number }
  system?: string
  feedback?: string
  timeoutMs: number
}

export type ComputerStepResult =
  // The model's next action(s), in order. The caller decides whether to run any of them (it should run at most the first).
  | { kind: 'actions'; actions: ComputerAction[]; callId: string; widthPx: number; heightPx: number; model: string; ms: number }
  // The model says it is finished (or cannot proceed) and proposes nothing.
  | { kind: 'done'; text: string; model: string; ms: number }
  // The provider raised a safety check. This is a stop that goes to the human queue; the port never acknowledges one.
  | { kind: 'blocked'; reason: string; model: string; ms: number }

export interface BootReport {
  ok: boolean
  provider: Provider
  // Concrete IDs from the environment ('' when unset).
  configured: ModelIds
  // Tiers whose env var is unset.
  unset: ModelTier[]
  // Tiers whose configured ID is not in the key's model list.
  missing: ModelTier[]
  // Chat/vision-capable model IDs the key can use (filtered; never the key).
  usable: string[]
  listed: number
  // Plain-English reason when not ok, including what to do next.
  problem?: string
}

export interface ModelPort {
  readonly provider: Provider
  models(): ModelIds
  // The general call; every verb below is built on it.
  complete(req: CompletionRequest): Promise<CompletionResult>
  // plan: slow, careful, structured when a schema is given.
  plan(messages: ChatMessage[], schema?: JsonSchemaSpec, opts?: { timeoutMs?: number }): Promise<unknown>
  // read: the quarantined reader. Raw untrusted content in, schema-checked fields out; no tools, never an action.
  read(untrusted: string, schema: JsonSchemaSpec, opts?: { timeoutMs?: number; instruction?: string }): Promise<unknown>
  // check: cheap verifier / classifier.
  check(prompt: string, schema: JsonSchemaSpec, opts?: { timeoutMs?: number }): Promise<unknown>
  // vision: one image plus a question.
  vision(image: ImageInput, prompt: string, schema?: JsonSchemaSpec, opts?: { timeoutMs?: number; tier?: ModelTier }): Promise<unknown>
  // computerStep: one action per turn from a fresh screenshot. A pending safety check is returned as `blocked`.
  computerStep(req: ComputerStepRequest): Promise<ComputerStepResult>
  // List what the key can use and check the configured IDs. Never throws.
  bootCheck(): Promise<BootReport>
}

// Low-level provider: what a backend must implement. `createModelPort` builds the verbs on top.
export interface ModelProvider {
  readonly provider: Provider
  models(): ModelIds
  complete(req: CompletionRequest): Promise<CompletionResult>
  computerStep(req: ComputerStepRequest): Promise<ComputerStepResult>
  bootCheck(): Promise<BootReport>
}

export type Log = (scope: string, ...args: unknown[]) => void
