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

  // A max_tokens stop means the JSON is truncated — JSON.parse would throw a
  // confusing "non-JSON text" error. Surface the real cause (and the fix) so the
  // resolver/query-set generator don't silently treat truncation as malformed.
  if (response.stop_reason === "max_tokens") {
    throw new Error(
      `Claude hit max_tokens (${maxTokens}) before completing the JSON — the output is ` +
        `truncated. Raise maxTokens for this extraction or shorten the input.`,
    );
  }

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

/**
 * Pull the first complete JSON value (object or array) out of free-form model
 * text, tolerating ```json fences and trailing prose. Pure — no network.
 *
 * We can't use `output_config.format` (json_schema) together with the web-search
 * server tool: structured outputs are documented as incompatible with citations,
 * which web-search results carry. So `researchJson` asks the model to END with a
 * JSON block and parses it out here instead. Scans brackets with string-awareness
 * so a `}` inside a quoted evidence string doesn't end the value early.
 */
export function extractJsonBlock(text: string): unknown {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const body = fenced?.[1] ?? text;
  const start = body.search(/[[{]/);
  if (start === -1) throw new Error("no JSON value found in model text");
  const open = body[start];
  const close = open === "{" ? "}" : "]";
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < body.length; i++) {
    const c = body[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === '"') inStr = false;
    } else if (c === '"') {
      inStr = true;
    } else if (c === open) {
      depth++;
    } else if (c === close) {
      depth--;
      if (depth === 0) return JSON.parse(body.slice(start, i + 1));
    }
  }
  throw new Error("unterminated JSON value in model text");
}

export interface ResearchOptions {
  model?: string;
  maxTokens?: number;
  /** Cap on server-side web searches (max_uses on the tool). */
  maxSearches?: number;
}

/**
 * One web-search-grounded call that returns a parsed JSON value. Enables the
 * `web_search_20250305` server tool (the basic variant — the only one available
 * on Haiku 4.5, this project's default model), lets Claude search, then parses
 * the JSON it ends with. Resumes across `pause_turn` (the server-tool loop cap).
 *
 * Used for questions that need CURRENT web knowledge the model can't have from
 * training (e.g. "was this company acquired?"). Throws if no JSON is produced —
 * callers decide the fallback (relationship guard keeps all competitors).
 */
export async function researchJson<T>(
  system: string,
  user: string,
  opts: ResearchOptions = {},
): Promise<T> {
  const model = opts.model ?? claudeModel();
  const maxTokens = opts.maxTokens ?? 3072;
  const maxUses = opts.maxSearches ?? 4;
  const tools = [
    { type: "web_search_20250305", name: "web_search", max_uses: maxUses },
  ] as unknown as Anthropic.Messages.MessageCreateParamsNonStreaming["tools"];

  const messages: Anthropic.MessageParam[] = [{ role: "user", content: user }];
  let response: Anthropic.Message | null = null;
  // Resume on pause_turn (server-tool loop hit its iteration cap); bounded so a
  // misbehaving loop can't spin forever.
  for (let hop = 0; hop < 6; hop++) {
    response = await client().messages.create({
      model,
      max_tokens: maxTokens,
      system,
      messages,
      tools,
    });
    if (response.stop_reason !== "pause_turn") break;
    messages.push({ role: "assistant", content: response.content });
  }
  if (!response) throw new Error("no response from Claude web-search call");

  const text = response.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("\n")
    .trim();
  if (!text) {
    throw new Error(
      `Claude web-search call returned no text (stop_reason=${String(response.stop_reason)}).`,
    );
  }
  return extractJsonBlock(text) as T;
}
