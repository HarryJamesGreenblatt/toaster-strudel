#!/usr/bin/env node
/**
 * assemble.js — Song IR -> idiomatic .strudel.js
 *
 * Reads a Song IR (../../song-ir/schema.json) and emits a named `let` block + a
 * `stack`, honoring each part's chosen_route:
 *
 *   reproduce | proxy  -> render[mode].pattern
 *   sample             -> render.sample.pattern (any `samples(...)` load is hoisted
 *                         to the top). If the sample WAV is not present locally it
 *                         falls back to render.proxy (unless --require-samples),
 *                         because asset availability is itself a routing signal.
 *   gap                -> skipped, with a comment.
 *
 * Usage:
 *   node assemble.js <song-ir.json> [--require-samples] [--out file.strudel.js]
 */
import fs from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2);
const irPath = argv.find((a) => !a.startsWith("--"));
const requireSamples = argv.includes("--require-samples");
const outIdx = argv.indexOf("--out");
const outPath = outIdx >= 0 ? argv[outIdx + 1] : null;

if (!irPath) {
  console.error("usage: node assemble.js <song-ir.json> [--require-samples] [--out f]");
  process.exit(2);
}

const ir = JSON.parse(fs.readFileSync(irPath, "utf8"));
const irDir = path.dirname(path.resolve(irPath));

const round = (n) => Math.round(n * 1000) / 1000;
const camel = (s) =>
  s.replace(/[-_ ]+(.)/g, (_, c) => c.toUpperCase()).replace(/[^a-zA-Z0-9]/g, "");

function hoistSamples(pattern) {
  const loads = [];
  const body = pattern.replace(/samples\(([^)]*)\)\s*;\s*/g, (_, inner) => {
    loads.push(inner.trim());
    return "";
  });
  return { loads, body: body.trim() };
}

function sampleAssetExists(ref) {
  if (!ref) return false;
  const roots = [irDir, process.cwd(), path.join(process.cwd(), "mir"),
                 path.join(process.cwd(), "assets", "samples")];
  return roots.some((r) => fs.existsSync(path.join(r, ref)));
}

const sampleLoads = new Set();
const partLines = [];
const varNames = [];
const notes = [];

for (const part of ir.parts) {
  const mode = part.chosen_route.mode;
  if (mode === "gap") {
    partLines.push(`   // [gap] ${part.id} — ${part.instrument?.name || ""}: no Strudel sound, skipped`);
    continue;
  }

  let render = part.render?.[mode];
  let usedMode = mode;

  if (mode === "sample") {
    const ref = part.render?.sample?.sample_ref;
    if (!sampleAssetExists(ref) && !requireSamples) {
      if (part.render?.proxy) {
        render = part.render.proxy;
        usedMode = "proxy";
        notes.push(`${part.id}: sample '${ref}' absent -> proxy fallback`);
      } else {
        partLines.push(`   // [sample missing] ${part.id}: '${ref}' not found (run sampleize.py); skipped`);
        notes.push(`${part.id}: sample missing, no proxy -> skipped`);
        continue;
      }
    }
  }

  if (!render || !render.pattern) {
    partLines.push(`   // [no render] ${part.id} (${usedMode})`);
    continue;
  }

  const { loads, body } = hoistSamples(render.pattern);
  loads.forEach((l) => sampleLoads.add(l));
  let expr = body;
  if (render.orbit != null && !/\.orbit\(/.test(expr)) expr += `.orbit(${render.orbit})`;

  const v = camel(part.id);
  varNames.push(v);
  const tag = usedMode === mode ? mode : `${mode}->${usedMode}`;
  partLines.push(`   ${v.padEnd(12)} = ${expr},   // ${tag} · ${part.instrument?.name || ""}`);
}

const setcpm = ir.render_target?.setcpm ?? ir.meta?.setcpm;
const out = [];
out.push(`// ${ir.context?.artist || ""} — ${ir.context?.title || ""}   (assembled from Song IR)`);
out.push(`// ${ir.meta?.key || ""} ${ir.meta?.mode || ""} · ${ir.meta?.tempo_bpm || ""} BPM · ${ir.meta?.feel || ""}`);
out.push(`setcpm(${round(setcpm)});`);
out.push("");
for (const l of sampleLoads) out.push(`samples(${l});`);
if (sampleLoads.size) out.push("");
out.push("let");
out.push(partLines.join("\n"));
out.push("");
const mg = ir.render_target?.master_gain;
const jamExpr = mg ? `stack(${varNames.join(", ")}).gain(${mg})` : `stack(${varNames.join(", ")})`;
out.push(`   jam          = ${jamExpr};`);
out.push("");
out.push("$: jam");

const text = out.join("\n") + "\n";
if (outPath) {
  fs.writeFileSync(outPath, text);
  console.error(`wrote ${outPath}`);
} else {
  process.stdout.write(text);
}
if (notes.length) console.error("\nnotes:\n  " + notes.join("\n  "));
