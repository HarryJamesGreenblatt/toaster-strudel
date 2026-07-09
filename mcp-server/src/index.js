#!/usr/bin/env node
// strudel-mcp — a lean "Strudel knowledge server".
//
// In the all-IDE workflow, the `cmillsdev.strudelvs` extension is the host: it
// runs the real Strudel engine in a VS Code webview and plays the active
// .strudel.js file (Ctrl+Enter play, Ctrl+. stop, all instruments, pianoroll).
// The agent composes into those files with normal editor tools.
//
// So this server no longer drives a browser or touches files. Its only job is to
// give the agent an authoritative, always-current grounding in the OFFICIAL
// Strudel API/docs, so composition matches the real language instead of memory.
//
// Transport is stdio — never write to stdout; logs go to stderr.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const log = (...a) => console.error("[strudel-mcp]", ...a);

const DOC_BASE = "https://strudel.cc";

// Friendly topic -> official docs path (strudel.cc/<path>/).
const TOPICS = {
  "mini-notation": "learn/mini-notation",
  "samples": "learn/samples",
  "effects": "learn/effects",
  "audio-effects": "learn/effects",
  "synths": "learn/synths",
  "tonal": "learn/tonal",
  "signals": "learn/signals",
  "random": "learn/random-modifiers",
  "conditional": "learn/conditional-modifiers",
  "time": "learn/time-modifiers",
  "time-modifiers": "learn/time-modifiers",
  "factories": "learn/factories",
  "accumulation": "learn/accumulation",
  "stepwise": "learn/stepwise",
  "code": "learn/code",
  "metadata": "learn/metadata",
  "input-output": "learn/input-output",
  "voicings": "understand/voicings",
  "pitch": "understand/pitch",
  "cycles": "understand/cycles",
  "value-modifiers": "functions/value-modifiers",
  "intro": "functions/intro",
  "recipes": "recipes/recipes",
  "getting-started": "workshop/getting-started",
};

function stripHtml(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const server = new McpServer({ name: "strudel-mcp", version: "0.2.0" });

server.tool(
  "strudel_docs",
  "Fetch OFFICIAL Strudel documentation to ground composition in the real API. " +
    "Pass a known topic key or a raw docs path like 'learn/effects'. Use this to " +
    "verify function names, mini-notation syntax, sampler/break techniques, tonal " +
    "helpers, etc. before writing patterns.",
  {
    topic: z
      .string()
      .describe(
        "A known topic (mini-notation, samples, effects, synths, tonal, signals, random, conditional, time, factories, accumulation, stepwise, voicings, value-modifiers, recipes, ...) or a strudel.cc docs path such as 'learn/tonal'."
      ),
  },
  async ({ topic }) => {
    const path = (TOPICS[topic] || topic).replace(/^\/+|\/+$/g, "");
    const url = `${DOC_BASE}/${path}/`;
    try {
      const res = await fetch(url, { headers: { "user-agent": "strudel-mcp" } });
      if (!res.ok) {
        return {
          content: [
            {
              type: "text",
              text: `Fetch failed (${res.status}) for ${url}.\nKnown topics: ${Object.keys(TOPICS).join(", ")}`,
            },
          ],
        };
      }
      const text = stripHtml(await res.text()).slice(0, 20000);
      return { content: [{ type: "text", text: `# ${url}\n\n${text}` }] };
    } catch (e) {
      return { content: [{ type: "text", text: `Error fetching ${url}: ${String(e)}` }] };
    }
  }
);

server.tool(
  "strudel_topics",
  "List the known Strudel documentation topics available via strudel_docs.",
  {},
  async () => ({ content: [{ type: "text", text: Object.keys(TOPICS).join("\n") }] })
);

server.resource("strudel-reference", "strudel://reference", async (uri) => ({
  contents: [
    {
      uri: uri.href,
      mimeType: "text/markdown",
      text: await readFile(resolve(__dirname, "reference.md"), "utf8"),
    },
  ],
}));

const transport = new StdioServerTransport();
await server.connect(transport);
log("Strudel knowledge server ready (strudel_docs + strudel://reference).");
