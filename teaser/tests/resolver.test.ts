/**
 * Unit tests for the PURE resolver helpers: profile normalization from Claude's
 * raw extraction, the labeled-markdown builder, and crawl4ai internal-link
 * picking. No network, no LLM.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildProfile,
  buildExtractionInput,
  isDefunctBrand,
} from "../src/resolver/Crawl4aiClaudeResolver.ts";
import { pickInternalTargets } from "../src/resolver/Crawl4aiClient.ts";
import {
  MIN_PROFILE_TEXT_CHARS,
  assertSufficientProfileText,
  profileTextLength,
} from "../src/resolver/profileExtraction.ts";

const FIXED = new Date("2026-06-22T00:00:00.000Z");

function extracted(over: Record<string, unknown> = {}) {
  return {
    name: "Acme",
    category: "CRM",
    competitors: [
      { name: "Salesforce", aliases: ["SFDC"] },
      { name: "HubSpot", aliases: [] },
    ],
    clientDomains: ["acme.io"],
    productClaims: [{ claim: "Free tier available", sourceUrl: "https://acme.io/pricing" }],
    ...over,
  } as Parameters<typeof buildProfile>[1];
}

test("buildProfile maps a clean extraction into the exact CompanyProfile shape", () => {
  const p = buildProfile("https://www.acme.io", extracted(), "claude-opus-4-8", FIXED);
  assert.equal(p.url, "https://www.acme.io");
  assert.equal(p.name, "Acme");
  assert.equal(p.category, "CRM");
  assert.equal(p.resolverModel, "claude-opus-4-8");
  assert.equal(p.resolvedAt, "2026-06-22T00:00:00.000Z");
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["Salesforce", "HubSpot"],
  );
  // Competitors ALWAYS come back unconfirmed — the human gate confirms them.
  for (const c of p.competitors) assert.equal(c.confirmed, false);
  assert.deepEqual(p.competitors[0]?.aliases, ["SFDC"]);
  assert.equal(p.productClaims.length, 1);
});

test("client host is always present in clientDomains (sans www, deduped)", () => {
  const p = buildProfile("https://www.acme.io", extracted({ clientDomains: ["acme.io", "ACME.io"] }), "m", FIXED);
  assert.deepEqual(p.clientDomains, ["acme.io"]);
});

test("blank name/category fall back to a hostname-derived brand", () => {
  const p = buildProfile(
    "https://acme-hq.io",
    extracted({ name: "  ", category: "" }),
    "m",
    FIXED,
  );
  assert.equal(p.name, "Acme Hq");
  assert.equal(p.category, "product");
});

test("competitors are de-duped case-insensitively and blanks dropped", () => {
  const p = buildProfile(
    "https://acme.io",
    extracted({
      competitors: [
        { name: "Salesforce", aliases: [] },
        { name: "salesforce", aliases: ["dup"] },
        { name: "  ", aliases: [] },
        { name: "HubSpot", aliases: [] },
      ],
    }),
    "m",
    FIXED,
  );
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["Salesforce", "HubSpot"],
  );
});

test("isDefunctBrand flags known-dead brands by name or alias, case-insensitively", () => {
  assert.equal(isDefunctBrand("Mint"), true);
  assert.equal(isDefunctBrand("mint.com"), true);
  assert.equal(isDefunctBrand("Budgeting App", ["Intuit Mint"]), true); // via alias
  assert.equal(isDefunctBrand("Monarch Money"), false); // live rival stays
  assert.equal(isDefunctBrand(""), false);
});

test("buildProfile drops defunct competitors (Mint) but keeps live ones", () => {
  const p = buildProfile(
    "https://copilot.money",
    extracted({
      competitors: [
        { name: "Mint", aliases: ["mint.com"] },
        { name: "YNAB", aliases: [] },
        { name: "Monarch Money", aliases: [] },
      ],
    }),
    "m",
    FIXED,
  );
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["YNAB", "Monarch Money"],
  );
});

test("buildProfile drops a defunct brand named only via an alias", () => {
  const p = buildProfile(
    "https://copilot.money",
    extracted({
      competitors: [
        { name: "The Mint App", aliases: ["Intuit Mint"] }, // alias is the dead brand
        { name: "YNAB", aliases: [] },
      ],
    }),
    "m",
    FIXED,
  );
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["YNAB"],
  );
});

test("product claims with an empty claim are dropped, text trimmed", () => {
  const p = buildProfile(
    "https://acme.io",
    extracted({
      productClaims: [
        { claim: "  ", sourceUrl: "x" },
        { claim: "  Costs $5/mo  ", sourceUrl: "  https://acme.io  " },
      ],
    }),
    "m",
    FIXED,
  );
  assert.equal(p.productClaims.length, 1);
  assert.equal(p.productClaims[0]?.claim, "Costs $5/mo");
  assert.equal(p.productClaims[0]?.sourceUrl, "https://acme.io");
});

test("buildExtractionInput labels each page with its url", () => {
  const input = buildExtractionInput([
    { url: "https://acme.io", markdown: "# Home" },
    { url: "https://acme.io/pricing", markdown: "# Pricing" },
  ]);
  assert.ok(input.includes("## https://acme.io\n\n# Home"));
  assert.ok(input.includes("## https://acme.io/pricing\n\n# Pricing"));
});

test("pickInternalTargets selects pricing-style links, deduped and capped", () => {
  const links = [
    { href: "https://acme.io/about", text: "About" },
    { href: "https://acme.io/pricing", text: "Pricing" },
    { href: "https://acme.io/pricing", text: "Pricing (dup)" },
    { href: "https://acme.io/x", text: "Alternatives to us" },
    { href: "https://acme.io/compare", text: "Compare" },
    { href: "https://acme.io/blog", text: "Blog" },
  ];
  const targets = pickInternalTargets(links, 2);
  assert.equal(targets.length, 2);
  assert.equal(targets[0], "https://acme.io/pricing");
  // second is matched by anchor text "Alternatives..." (the /x href)
  assert.equal(targets[1], "https://acme.io/x");
});

test("pickInternalTargets returns [] when nothing matches", () => {
  const targets = pickInternalTargets(
    [
      { href: "https://acme.io/about", text: "About" },
      { href: "https://acme.io/blog", text: "Blog" },
    ],
    3,
  );
  assert.deepEqual(targets, []);
});

test("profileTextLength sums trimmed readable chars across pages", () => {
  assert.equal(profileTextLength(["  hello  ", "world!"]), "hello".length + "world!".length);
  assert.equal(profileTextLength([]), 0);
  assert.equal(profileTextLength(["   ", ""]), 0);
});

test("assertSufficientProfileText throws on a thin challenge page (fails safe)", () => {
  // A Cloudflare interstitial served at HTTP 200 — a few words of noise.
  const challenge = "Just a moment... Enable JavaScript and cookies to continue.";
  assert.ok(challenge.length < MIN_PROFILE_TEXT_CHARS);
  assert.throws(
    () => assertSufficientProfileText([challenge], "https://calai.app"),
    /insufficient content to profile/,
  );
  assert.throws(() => assertSufficientProfileText([], "https://x.com"), /insufficient content/);
});

test("assertSufficientProfileText passes a real page with enough text", () => {
  const real = "Cal AI is an AI-powered calorie tracking app for your phone. ".repeat(6);
  assert.ok(real.length >= MIN_PROFILE_TEXT_CHARS);
  assertSufficientProfileText([real], "https://calai.app"); // must not throw
});
