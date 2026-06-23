/**
 * Thin Claude wrapper for structured extraction.
 *
 * One function: `extractJson` takes a system prompt, user content, and a JSON
 * schema, and returns the parsed object. It uses the official @anthropic-ai/sdk
 * with `output_config.format` (json_schema) to constrain the response, then
 * finds the text content block and JSON.parses it.
 *
 * Model comes from TEASER_CLAUDE_MODEL (default "claude-haiku-4-5"); the API key
 * is the platform's own ANTHROPIC_API_KEY (no new key var). We do NOT pass
 * temperature/top_p/top_k/budget_tokens; thinking is omitted. Haiku 4.5 supports
 * output_config json_schema structured outputs, which is all this wrapper needs —
 * a much cheaper/faster model for the teaser extraction calls than opus.
 *
 * No network happens at module load — the client is built lazily on first call.
 */

import Anthropic from "@anthropic-ai/sdk";

export const DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5";

/** Resolve the model id from env, falling back to haiku-4-5. */
export function claudeModel(): string {
  const m = process.env.TEASER_CLAUDE_MODEL;
  return m && m.trim() ? m.trim() : DEFAULT_CLAUDE_MODEL;
}

/** True once an Anthropic key is configured (used by config gating). */
export function hasClaudeKey(): boolean {
  return Boolean(process.env.ANTHROPIC_API_KEY);
}

let cachedClient: Anthropic | null = null;

function client(): Anthropic {
  if (cachedClient) return cachedClient;
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error(
      "ANTHROPIC_API_KEY is not set — the Claude resolver/query-set generator needs it.",
    );
  }
  cachedClient = new Anthropic({ apiKey });
  return cachedClient;
}

/**
 * A JSON Schema object. Every object in the schema must set
 * `additionalProperties: false` and list all of its fields in `required` (the
 * structured-output contract). We keep the type loose so callers can pass a
 * literal schema without fighting the type system.
 */
export type JsonSchema = Record<string, unknown>;

export interface ExtractOptions {
  /** Per-call override of the model (defaults to claudeModel()). */
  model?: string;
  /** Generous default so structured output isn't truncated. */
  maxTokens?: number;
}

/**
 * Run one structured-extraction call and return the parsed JSON object.
 *
 * @param system  the system prompt (the extraction/generation instructions)
 * @param user    the user content (the markdown / profile to operate on)
 * @param schema  a JSON schema; the response is constrained to match it
 */
export async function extractJson<T>(
  system: string,
  user: string,
  schema: JsonSchema,
  opts: ExtractOptions = {},
): Promise<T> {
  const model = opts.model ?? claudeModel();
  const maxTokens = opts.maxTokens ?? 4096;

  const response = await client().messages.create({
    model,
    max_tokens: maxTokens,
    system,
    messages: [{ role: "user", content: user }],
    // Constrain the output to the schema. The API guarantees the text block is
    // valid JSON matching `schema` (additionalProperties:false + all-required).
    output_config: { format: { type: "json_schema", schema } },
  });

  // Find the text content block (responses may interleave thinking/text blocks).
  let text: string | null = null;
  for (const block of response.content) {
    if (block.type === "text") {
      text = block.text;
      break;
    }
  }
  if (text === null) {
    throw new Error(
      `Claude returned no text block (stop_reason=${String(response.stop_reason)}).`,
    );
  }

  try {
    return JSON.parse(text) as T;
  } catch (err) {
    const snippet = text.slice(0, 500);
    throw new Error(
      `Claude returned non-JSON text despite json_schema format: ${snippet}` +
        (err instanceof Error ? ` (${err.message})` : ""),
    );
  }
}
