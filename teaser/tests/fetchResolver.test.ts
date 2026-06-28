import assert from "node:assert/strict";
import { test } from "node:test";
import {
  isBlockedIp,
  htmlToText,
  pickSecondaryUrl,
  buildExtractionInput,
} from "../src/resolver/FetchClaudeResolver.ts";

test("isBlockedIp blocks private/reserved/loopback ranges", () => {
  for (const ip of [
    "127.0.0.1",
    "10.0.0.5",
    "172.16.4.4",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.169.254", // cloud metadata
    "100.64.0.1", // CGNAT
    "0.0.0.0",
    "::1",
    "fe80::1",
    "fd00::1",
    "::ffff:127.0.0.1", // v4-mapped loopback
    "not-an-ip",
  ]) {
    assert.equal(isBlockedIp(ip), true, `${ip} should be blocked`);
  }
});

test("isBlockedIp allows public addresses", () => {
  for (const ip of ["8.8.8.8", "1.1.1.1", "172.15.0.1", "172.32.0.1", "2606:4700:4700::1111"]) {
    assert.equal(isBlockedIp(ip), false, `${ip} should be allowed`);
  }
});

test("htmlToText drops scripts/styles, keeps title + prose", () => {
  const html =
    "<html><head><title>Anoria — Emotion AI</title><style>.x{}</style></head>" +
    "<body><script>evil()</script><h1>Read your emotions</h1>" +
    "<p>The wearable that tracks how you feel &amp; why.</p></body></html>";
  const text = htmlToText(html);
  assert.ok(text.startsWith("Anoria — Emotion AI"), "title leads");
  assert.ok(text.includes("Read your emotions"));
  assert.ok(text.includes("tracks how you feel & why."), "entities decoded");
  assert.ok(!/evil\(\)|\.x\{\}/.test(text), "script/style content gone");
  assert.ok(!text.includes("<"), "no tags remain");
});

test("pickSecondaryUrl finds a same-origin pricing/compare/about link", () => {
  const html =
    '<a href="/about">About</a><a href="https://x.com/pricing">Pricing</a>' +
    '<a href="https://other.com/compare">Other</a>';
  const got = pickSecondaryUrl(html, "https://x.com/");
  // First match wins; /about is same-origin and matches.
  assert.equal(got, "https://x.com/about");
});

test("pickSecondaryUrl ignores cross-origin and homepage links", () => {
  const html = '<a href="https://other.com/pricing">x</a><a href="/">home</a>';
  assert.equal(pickSecondaryUrl(html, "https://x.com/"), null);
});

test("buildExtractionInput labels each page with its url", () => {
  const out = buildExtractionInput([
    { url: "https://x.com", text: "home" },
    { url: "https://x.com/pricing", text: "pricing" },
  ]);
  assert.ok(out.includes("## https://x.com\n\nhome"));
  assert.ok(out.includes("## https://x.com/pricing\n\npricing"));
});
