// Shared helpers for the grounding spike. Never prints the API key.
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(here, '../..');
dotenv.config({ path: path.join(REPO, '.env'), quiet: true });

export function makeClient() {
  if (!process.env.GEMINI_API_KEY) throw new Error('GEMINI_API_KEY missing in REPO/.env');
  return new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
}

let calls = 0;
export const callCount = () => calls;

/** Thin wrapper: timing + call counter + hard timeout. */
export async function timed(client, params, { timeoutMs = 60000 } = {}) {
  calls += 1;
  const t0 = performance.now();
  try {
    const interaction = await client.interactions.create(params, { signal: AbortSignal.timeout(timeoutMs) });
    return { ok: true, interaction, ms: Math.round(performance.now() - t0) };
  } catch (e) {
    return { ok: false, error: String(e?.message ?? e).slice(0, 500), status: e?.status, ms: Math.round(performance.now() - t0) };
  }
}

export function outputText(interaction) {
  if (typeof interaction.output_text === 'string') return interaction.output_text;
  const parts = [];
  for (const s of interaction.steps ?? []) {
    if (s.type === 'model_output') for (const c of s.content ?? []) if (c.type === 'text') parts.push(c.text);
  }
  return parts.join('');
}

export function functionCalls(interaction) {
  return (interaction.steps ?? []).filter((s) => s.type === 'function_call');
}

export function usageOf(interaction) {
  const u = interaction.usage ?? {};
  return { in: u.total_input_tokens, out: u.total_output_tokens, thought: u.total_thought_tokens, total: u.total_tokens };
}

export const BOX_SCHEMA = {
  type: 'object',
  properties: {
    found: { type: 'boolean', description: 'true only if the described element is clearly visible on screen' },
    box_2d: {
      type: 'array',
      items: { type: 'integer' },
      description: 'Bounding box as [ymin, xmin, ymax, xmax], integers normalised to 0-1000. [0,0,0,0] when found is false.',
    },
    label: { type: 'string', description: 'What the element is, as seen on screen' },
    reason: { type: 'string', description: 'Short reason, especially when found is false' },
  },
  required: ['found', 'box_2d', 'label', 'reason'],
};
