// Analyze the percussion rhythm of a MIDI drum track (GM channel 10).
// Breaks the kit apart per-instrument and reports, for each, WHERE within the
// beat its hits land — revealing straight-16th vs triplet/swing feel.
//
//   node src/analyze-drums.js <file.mid> [trackIndex=0]

import fs from "node:fs";
import pkg from "@tonejs/midi";
const { Midi } = pkg;

const file = process.argv[2];
const trackIdx = Number(process.argv[3] ?? 0);
if (!file) { console.error("usage: node src/analyze-drums.js <file.mid> [track]"); process.exit(1); }

const midi = new Midi(fs.readFileSync(file));
const ppq = midi.header.ppq;
const track = midi.tracks[trackIdx];
const secPerBeat = () => 60 / (midi.header.tempos[0]?.bpm ?? 120);

// GM percussion map (the common ones)
const GM = {
  35: "AcousticBass", 36: "Kick", 37: "SideStick/Rim", 38: "Snare", 39: "Clap",
  40: "ElecSnare", 41: "LowTom", 42: "ClosedHat", 43: "HiFloorTom", 44: "PedalHat",
  45: "LowTom2", 46: "OpenHat", 47: "LowMidTom", 48: "HiMidTom", 49: "Crash",
  50: "HiTom", 51: "Ride", 53: "RideBell", 54: "Tambourine", 55: "Splash",
  56: "Cowbell", 60: "HiBongo", 61: "LowBongo", 62: "MuteConga", 63: "OpenConga",
  64: "LowConga", 65: "HiTimbale", 66: "LowTimbale", 67: "HiAgogo", 68: "LowAgogo",
  69: "Cabasa", 70: "Maracas", 71: "ShortWhistle", 72: "LongWhistle",
  73: "ShortGuiro", 74: "LongGuiro", 75: "Claves", 76: "HiWoodblock",
  77: "LowWoodblock", 78: "MuteCuica", 79: "OpenCuica", 80: "MuteTriangle",
  81: "OpenTriangle", 82: "Shaker",
};

// bucket every note by instrument; record its phase within a beat (0..1)
const byInst = new Map();
const ticksPerBeat = ppq;
for (const n of track.notes) {
  const name = GM[n.midi] ?? `note${n.midi}`;
  const tick = Math.round(n.ticks);
  const beatPhase = (tick % ticksPerBeat) / ticksPerBeat; // 0..1 within the beat
  const barPhase = (tick % (ticksPerBeat * 4)) / (ticksPerBeat * 4); // 0..1 within bar
  if (!byInst.has(name)) byInst.set(name, []);
  byInst.get(name).push({ beatPhase, barPhase });
}

// classify a phase: nearest straight-16th vs nearest triplet-8th
function classify(phase) {
  const straight = [0, .25, .5, .75];
  const triplet = [0, 1/3, 2/3];
  const near = (arr) => Math.min(...arr.map(p => Math.abs(phase - p)), Math.abs(phase - 1));
  return { straightErr: near(straight), tripletErr: near(triplet) };
}

console.log(`file=${file}  track=${trackIdx}  ppq=${ppq}  bpm=${(midi.header.tempos[0]?.bpm ?? 120).toFixed(1)}`);
console.log(`total drum notes: ${track.notes.length}\n`);

// sort instruments by note count desc
const rows = [...byInst.entries()].sort((a, b) => b[1].length - a[1].length);
for (const [name, hits] of rows) {
  if (hits.length < 8) continue;
  // 16-step bar histogram
  const grid = new Array(16).fill(0);
  for (const h of hits) grid[Math.round(h.barPhase * 16) % 16]++;
  const maxc = Math.max(...grid);
  const bars = grid.map(c => c === 0 ? "." : c > maxc * 0.6 ? "X" : "x").join("");

  // swing/triplet verdict from beat-phase errors
  let sErr = 0, tErr = 0;
  for (const h of hits) { const c = classify(h.beatPhase); sErr += c.straightErr; tErr += c.tripletErr; }
  sErr /= hits.length; tErr /= hits.length;
  const verdict = tErr < sErr * 0.8 ? "TRIPLET/swung" : sErr < tErr * 0.8 ? "straight" : "mixed";

  // measure actual mean phase of the offbeat hits (to quantify swing depth)
  console.log(`${name.padEnd(16)} n=${String(hits.length).padStart(4)}  |${bars}|  feel=${verdict}  (straightErr=${sErr.toFixed(3)} tripletErr=${tErr.toFixed(3)})`);
}

console.log("\nGrid = one bar in 16ths.  X=strong hit, x=weak, .=rest.");
console.log("feel: compares each hit's distance to straight-16th vs triplet positions.");
