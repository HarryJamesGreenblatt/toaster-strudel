#!/usr/bin/env node
// tab2strudel — convert song data into a Strudel `note(...)` line.
//
// Multi-mode importer. Auto-detects the source format by file extension:
//   .mid / .midi                          -> MIDI          (via @tonejs/midi)
//   .gp / .gp3 / .gp4 / .gp5 / .gpx / .gp7 -> Guitar Pro    (via alphaTab)
//   .xml / .musicxml / .mxl / .cap        -> MusicXML/etc.  (via alphaTab)
//
// Format tradeoff:
//   MIDI       — most abundant; accurate pitch + rhythm + tuning; NO articulation.
//   Guitar Pro — richest for guitar; carries palm mute / tremolo / bends (feel).
//   MusicXML   — open standard (MuseScore); notation + most techniques.
//
// Usage:
//   node src/tab2strudel.js <file>              [options]
//   node src/tab2strudel.js --fetch "<artist song>" [--pick n] [--out file.mid]
//   node src/tab2strudel.js <file> --format <midi|tab>   (override auto-detect)
//
// Fetching (grabs a MIDI from the BitMidi public archive):
//   --fetch <query>    Search BitMidi. With no --pick, LISTS candidates and exits.
//   --pick <n>         Download candidate n from the last search, then convert it.
//   --out <path>       Where to save the downloaded .mid (default: <slug>.mid).
//   --download-only    Download the picked file but skip conversion.
//
// Options (both modes):
//   --track <n>        Track index to convert (default: track with most notes).
//   --list             List tracks (index, name, instrument/tuning, note count) and exit.
//   --grid <n>         Steps per QUARTER note (default 4 => 16th-note grid).
//   --bars <n>         Limit output to the first N bars (default: all).
//   --skip <n>         Skip the first N bars before capturing (default: 0).
//   --mono <high|low>  Reduce chords to one note per step (default: keep as [a,b] stack).
//   --min <note>       Drop notes below this pitch, e.g. e2 (default: none).
//   --max <note>       Drop notes above this pitch, e.g. c6 (default: none).
//   --name <ident>     Variable name for the emitted let-binding (default: riff).
//   --emit <inline|arrange>  inline = one note("<...>") line (default; good for short
//                      riffs). arrange = editable bars[] array + arrange() scaffold for
//                      complex multi-section pieces you group into sections by hand.
//
// Output: prints a ready-to-paste Strudel snippet to stdout (logs go to stderr).

import { readFile, writeFile } from "node:fs/promises";
import { extname } from "node:path";
import midiPkg from "@tonejs/midi";
const { Midi } = midiPkg;

const BITMIDI = "https://bitmidi.com";
const NOTE_NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"];
const TAB_EXTS = new Set([".gp", ".gp3", ".gp4", ".gp5", ".gpx", ".gp7", ".xml", ".musicxml", ".mxl", ".cap", ".capx"]);

const log = (...a) => console.error("[tab2strudel]", ...a);

function midiToName(m) {
  const octave = Math.floor(m / 12) - 1; // MIDI 60 = C4
  return NOTE_NAMES[m % 12] + octave;
}

function nameToMidi(name) {
  const m = String(name).trim().toLowerCase().match(/^([a-g])(#|s|b)?(-?\d+)$/);
  if (!m) throw new Error(`Bad note name: ${name}`);
  const base = { c: 0, d: 2, e: 4, f: 5, g: 7, a: 9, b: 11 }[m[1]];
  const accidental = m[2] === "b" ? -1 : m[2] ? 1 : 0;
  return base + accidental + (parseInt(m[3], 10) + 1) * 12;
}

function parseArgs(argv) {
  const opts = {
    file: null, track: null, list: false, grid: 4, bars: null, skip: 0,
    mono: null, min: null, max: null, name: "riff", format: null, emit: "inline",
    fetch: null, pick: null, out: null, downloadOnly: false,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--list") opts.list = true;
    else if (a === "--emit") opts.emit = argv[++i];
    else if (a === "--fetch") opts.fetch = argv[++i];
    else if (a === "--pick") opts.pick = parseInt(argv[++i], 10);
    else if (a === "--out") opts.out = argv[++i];
    else if (a === "--download-only") opts.downloadOnly = true;
    else if (a === "--format") opts.format = argv[++i];
    else if (a === "--track") opts.track = parseInt(argv[++i], 10);
    else if (a === "--grid") opts.grid = parseInt(argv[++i], 10);
    else if (a === "--bars") opts.bars = parseInt(argv[++i], 10);
    else if (a === "--skip") opts.skip = parseInt(argv[++i], 10);
    else if (a === "--mono") opts.mono = argv[++i];
    else if (a === "--min") opts.min = nameToMidi(argv[++i]);
    else if (a === "--max") opts.max = nameToMidi(argv[++i]);
    else if (a === "--name") opts.name = argv[++i];
    else if (a.startsWith("--")) throw new Error(`Unknown option: ${a}`);
    else rest.push(a);
  }
  opts.file = rest[0] ?? null;
  return opts;
}

// --- BitMidi fetch --------------------------------------------------------

async function searchBitMidi(query) {
  const url = `${BITMIDI}/api/midi/search?q=${encodeURIComponent(query)}`;
  const res = await fetch(url, { headers: { "user-agent": "tab2strudel" } });
  if (!res.ok) throw new Error(`BitMidi search failed (${res.status})`);
  const json = await res.json();
  return json?.result?.results ?? [];
}

async function download(url, out) {
  const res = await fetch(url, { headers: { "user-agent": "tab2strudel" } });
  if (!res.ok) throw new Error(`Download failed (${res.status}) for ${url}`);
  await writeFile(out, Buffer.from(await res.arrayBuffer()));
  return out;
}

function safeName(s) {
  return String(s || "track").replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "track";
}

// --- Producers: source -> intermediate representation ---------------------
// IR = { bpm, stepsPerBar, steps: Map<stepIndex, Set<midi>>, maxStep, label, feel }

async function irFromMidi(data, opts) {
  const midi = new Midi(data);
  const ppq = midi.header.ppq;
  const bpm = midi.header.tempos[0]?.bpm ?? 120;
  const ts = midi.header.timeSignatures[0]?.timeSignature ?? [4, 4];
  const beatsPerBar = ts[0] * (4 / ts[1]);

  if (opts.list) {
    log(`ppq=${ppq}  bpm=${bpm.toFixed(2)}  timeSig=${ts[0]}/${ts[1]}`);
    midi.tracks.forEach((t, i) =>
      log(`  [${i}] "${t.name || "(unnamed)"}"  instrument=${t.instrument?.name || "?"}  notes=${t.notes.length}`)
    );
    return null;
  }

  let trackIdx = opts.track;
  if (trackIdx == null) {
    trackIdx = midi.tracks.reduce((best, t, i, arr) => (t.notes.length > arr[best].notes.length ? i : best), 0);
    log(`No --track given; auto-picked track ${trackIdx} (most notes).`);
  }
  const track = midi.tracks[trackIdx];
  if (!track) throw new Error(`No track ${trackIdx} (file has ${midi.tracks.length}).`);

  const stepTicks = ppq / opts.grid;
  const stepsPerBar = Math.round(beatsPerBar * opts.grid);
  const skipTicks = opts.skip * stepsPerBar * stepTicks;

  const steps = new Map();
  let maxStep = 0;
  for (const n of track.notes) {
    if (opts.min != null && n.midi < opts.min) continue;
    if (opts.max != null && n.midi > opts.max) continue;
    const rel = n.ticks - skipTicks;
    if (rel < 0) continue;
    const step = Math.round(rel / stepTicks);
    if (opts.bars != null && step >= opts.bars * stepsPerBar) continue;
    if (!steps.has(step)) steps.set(step, new Set());
    steps.get(step).add(n.midi);
    if (step > maxStep) maxStep = step;
  }
  return { bpm, stepsPerBar, steps, maxStep, label: `MIDI track ${trackIdx} "${track.name || ""}"`, feel: null };
}

function beatQuarters(beat) {
  const d = beat.duration; // alphaTab Duration enum (Quarter=4, Eighth=8, ...)
  let q = d > 0 ? 4 / d : 4;
  const dots = beat.dots || 0;
  if (dots === 1) q *= 1.5;
  else if (dots >= 2) q *= 1.75;
  const tn = beat.tupletNumerator || 1;
  const td = beat.tupletDenominator || 1;
  if (tn > 1) q *= td / tn;
  return q;
}

function countTabNotes(track) {
  let c = 0;
  for (const st of track.staves || []) for (const bar of st.bars || []) for (const v of bar.voices || []) for (const b of v.beats || []) c += (b.notes || []).length;
  return c;
}

async function irFromTab(data, opts) {
  const mod = await import("@coderline/alphatab");
  const AT = mod.default ?? mod;
  const ScoreLoader = AT.importer?.ScoreLoader ?? AT.ScoreLoader;
  if (!ScoreLoader) throw new Error("alphaTab ScoreLoader not found (unexpected package layout).");
  const score = ScoreLoader.loadScoreFromBytes(new Uint8Array(data));
  const bpm = score.tempo || 120;

  if (opts.list) {
    log(`title="${score.title || ""}"  bpm=${bpm}  tracks=${score.tracks.length}`);
    score.tracks.forEach((t, i) => {
      const tuning = t.staves?.[0]?.tuning;
      const tun = Array.isArray(tuning) && tuning.length ? ` tuning=[${tuning.map(midiToName).join(" ")}]` : "";
      log(`  [${i}] "${t.name || "(unnamed)"}"  notes=${countTabNotes(t)}${tun}`);
    });
    return null;
  }

  let trackIdx = opts.track;
  if (trackIdx == null) {
    trackIdx = score.tracks.reduce((best, t, i, arr) => (countTabNotes(t) > countTabNotes(arr[best]) ? i : best), 0);
    log(`No --track given; auto-picked track ${trackIdx} (most notes).`);
  }
  const track = score.tracks[trackIdx];
  if (!track) throw new Error(`No track ${trackIdx} (file has ${score.tracks.length}).`);
  const stave = track.staves?.[0];
  if (!stave) throw new Error(`Track ${trackIdx} has no staves.`);

  // Constant bar geometry from the first (post-skip) master bar.
  const grid = opts.grid;
  const mb0 = score.masterBars?.[opts.skip] ?? score.masterBars?.[0];
  const num = mb0?.timeSignatureNumerator ?? 4;
  const den = mb0?.timeSignatureDenominator ?? 4;
  const stepsPerBar = Math.round(num * (4 / den) * grid);

  const steps = new Map();
  let maxStep = 0;
  const feel = { palmMute: false, tremolo: false, bend: false, vibrato: false };

  const bars = stave.bars || [];
  for (let bi = 0; bi < bars.length; bi++) {
    if (bi < opts.skip) continue;
    const outBar = bi - opts.skip;
    if (opts.bars != null && outBar >= opts.bars) break;
    const voice = bars[bi].voices?.[0];
    if (!voice) continue;
    let cursor = 0;
    for (const beat of voice.beats || []) {
      const s = Math.max(1, Math.round(beatQuarters(beat) * grid));
      if (!beat.isRest && (beat.notes || []).length) {
        const set = new Set();
        for (const n of beat.notes) {
          const midi = n.realValue;
          if (midi == null) continue;
          if (opts.min != null && midi < opts.min) continue;
          if (opts.max != null && midi > opts.max) continue;
          set.add(midi);
          if (n.isPalmMute) feel.palmMute = true;
          if (n.hasBend || n.bendType) feel.bend = true;
          if (n.vibrato) feel.vibrato = true;
        }
        if (beat.isTremolo || beat.tremoloSpeed != null) feel.tremolo = true;
        if (beat.vibrato) feel.vibrato = true;
        if (set.size) {
          const idx = outBar * stepsPerBar + cursor;
          steps.set(idx, set);
          if (idx > maxStep) maxStep = idx;
        }
      }
      cursor += s;
    }
  }
  return { bpm, stepsPerBar, steps, maxStep, label: `Tab track ${trackIdx} "${track.name || ""}"`, feel };
}

// --- Shared renderer: IR -> Strudel snippet -------------------------------

function render(ir, opts) {
  const { bpm, stepsPerBar, steps, maxStep, label, feel } = ir;
  if (steps.size === 0) {
    log("No notes captured with these filters. Try --list, a different --track, or wider --min/--max.");
    process.exit(2);
  }
  const totalBars = opts.bars ?? Math.ceil((maxStep + 1) / stepsPerBar);

  const bars = [];
  for (let b = 0; b < totalBars; b++) {
    const cells = [];
    for (let s = 0; s < stepsPerBar; s++) {
      const set = steps.get(b * stepsPerBar + s);
      if (!set || set.size === 0) {
        cells.push("~");
        continue;
      }
      let midis = [...set].sort((a, z) => a - z);
      if (opts.mono === "high") midis = [midis[midis.length - 1]];
      else if (opts.mono === "low") midis = [midis[0]];
      const names = midis.map(midiToName);
      cells.push(names.length > 1 ? `[${names.join(",")}]` : names[0]);
    }
    bars.push(`[${cells.join(" ")}]`);
  }

  // --emit arrange: bars as an editable array + an arrange(...) scaffold, so a
  // complex multi-section piece can be grouped into named sections by hand.
  // (The tool nails notes-per-bar; verse/chorus boundaries are a musical call.)
  if (opts.emit === "arrange") {
    const arrName = `${opts.name}Bars`;
    const lines = bars.map((b, i) => `  ${JSON.stringify(b)}, // ${i}`).join("\n");
    const out =
      `setcpm(${Math.round(bpm)}/4)\n\n` +
      `// ${label}: ${bars.length} bars @ ${opts.grid} steps/quarter, ${bpm.toFixed(1)} bpm.\n` +
      `// Each entry = one bar (1 cycle). Group indices into sections, then arrange().\n` +
      `const ${arrName} = [\n${lines}\n];\n\n` +
      `// Default plays bars in order. Replace with section groupings, e.g.\n` +
      `//   const A = ${arrName}.slice(0, 4).join(" ");   // 4-bar phrase\n` +
      `//   const B = ${arrName}.slice(4, 8).join(" ");\n` +
      `//   arrange([2, A], [2, B], [2, A], ...)\n` +
      `let ${opts.name} = arrange(...${arrName}.map((b) => [1, b]))\n` +
      `              .note()\n` +
      `              .s("gm_pad_halo")\n` +
      `              .gain(0.6);\n\n` +
      `$: ${opts.name}.pianoroll()\n`;
    log(`${label} -> ${bars.length} bars (arrange emit).`);
    process.stdout.write(out);
    return;
  }

  const seq = bars.length === 1 ? bars[0].slice(1, -1) : `<${bars.join(" ")}>`;

  // Feel hints: from tab we know which techniques exist; from MIDI we don't.
  const detected = feel ? Object.entries(feel).filter(([, v]) => v).map(([k]) => k) : null;
  const feelLine = feel == null
    ? `              // No technique metadata (MIDI source). Add feel by hand:\n`
    : detected.length
      ? `              // Detected in source: ${detected.join(", ")}. Map to Strudel:\n`
      : `              // Tab source, no techniques flagged. Add feel by hand:\n`;

  const snippet =
    `setcpm(${Math.round(bpm)}/4)\n\n` +
    `let ${opts.name} = note("${seq}")\n` +
    `              .s("gm_distortion_guitar")\n` +
    feelLine +
    `              //   tremolo  -> *8/*16 subdivisions or .stut\n` +
    `              //   palmMute -> .clip(0.4).release(0.06)\n` +
    `              //   overdrive-> .shape(0.3) / .distort("1.2")\n` +
    `              //   bend     -> .slide  |  vibrato -> .vib\n` +
    `              .gain(0.6);\n\n` +
    `$: ${opts.name}.pianoroll()\n`;

  log(`${label} -> ${totalBars} bar(s) @ ${opts.grid} steps/quarter, ${bpm.toFixed(1)} bpm.`);
  process.stdout.write(snippet);
}

function detectMode(opts) {
  if (opts.format) return opts.format === "tab" ? "tab" : "midi";
  const ext = extname(opts.file).toLowerCase();
  if (ext === ".mid" || ext === ".midi") return "midi";
  if (TAB_EXTS.has(ext)) return "tab";
  return "midi"; // fetched files and unknowns default to MIDI
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));

  if (opts.fetch) {
    const results = await searchBitMidi(opts.fetch);
    if (results.length === 0) {
      log(`No MIDI results for "${opts.fetch}". Try a looser query (artist OR title).`);
      process.exit(2);
    }
    if (opts.pick == null) {
      log(`Found ${results.length} candidate(s) for "${opts.fetch}" — re-run adding --pick <n>:`);
      results.forEach((r, i) => log(`  [${i}] ${r.name}  (views=${r.views})`));
      return;
    }
    const chosen = results[opts.pick];
    if (!chosen) {
      log(`No candidate at --pick ${opts.pick} (valid range 0..${results.length - 1}).`);
      process.exit(2);
    }
    const out = opts.out || `${safeName(chosen.slug)}.mid`;
    await download(`${BITMIDI}${chosen.downloadUrl}`, out);
    log(`Downloaded "${chosen.name}" -> ${out}`);
    opts.file = out;
    if (opts.downloadOnly) return;
  }

  if (!opts.file) {
    log('Usage: node src/tab2strudel.js <file>  |  --fetch "<artist song>" [--pick n]');
    log("       Supports .mid/.midi, .gp*/.gpx (Guitar Pro), .xml/.musicxml/.mxl (MusicXML).");
    log("       [--list] [--track n] [--grid 4] [--bars n] [--skip n] [--mono high|low] [--min e2] [--max c6] [--name riff] [--format midi|tab]");
    process.exit(1);
  }

  const data = await readFile(opts.file);
  const mode = detectMode(opts);
  const ir = mode === "tab" ? await irFromTab(data, opts) : await irFromMidi(data, opts);
  if (ir === null) return; // --list already printed
  render(ir, opts);
}

main().catch((e) => {
  log("Error:", e.message);
  process.exit(1);
});
