# toaster-strudel

<p align="center">
  <img src="assets/images/toaster-strudel-cover.png" alt="Toaster Strudel — AI music, together. A conductor pastry mascot beside a toaster pastry iced with a musical note." width="640">
</p>

Tools and knowledge for **AI-assisted [Strudel](https://strudel.cc) composition** —
grounded in the real Strudel API, and in the *actual rhythms of real music* rather
than guesswork.

The guiding idea: don't approximate a genre from its name. **Measure it.** Pull real
performance data (MIDI today, sampled audio via MIR next), analyze the groove
per-instrument, and translate the verified pattern into Strudel.

## Layout

```
toaster-strudel/
├─ mcp-server/        Node MCP server: Strudel docs/knowledge + data importers
│  └─ src/
│     ├─ index.js         MCP server (strudel_docs, strudel_topics, reference)
│     ├─ reference.md     Strudel cheat sheet (served as a resource)
│     ├─ tab2strudel.js   MIDI / Guitar Pro / MusicXML → Strudel, + BitMidi fetch
│     └─ analyze-drums.js GM drum track → per-instrument grid + swing/triplet feel
├─ mir/              (planned) Python MIR sidecar: audio → tempo/beats/stems/MIDI
├─ jams/             personal WIP patterns          (gitignored)
├─ arrangements/     personal WIP arrangements       (gitignored)
└─ .vscode/mcp.json  wires the MCP server into VS Code
```

## Workflow

- **Host:** the [`cmillsdev.strudelvs`](https://marketplace.visualstudio.com/items?itemName=cmillsdev.strudelvs)
  VS Code extension runs the real Strudel engine in a webview and plays the active
  `.strudel.js` file — **Ctrl+Enter** play, **Ctrl+.** stop — with all instruments,
  pianoroll, and live highlighting.
- **Compose:** edit `.strudel.js` files with normal editor tools; press Ctrl+Enter.
- **Ground:** consult the `strudel_docs` MCP tool for the real API before writing.
- **Verify:** analyze real performances to learn a genre's rhythmic nuance instead
  of guessing (see `mcp-server/src/analyze-drums.js`).

## Importers

```powershell
cd mcp-server
npm install

# Fetch a real MIDI from BitMidi, then break its drum track down per-instrument
node src/tab2strudel.js --fetch "cumbia" --pick 0 --out clip.mid
node src/analyze-drums.js clip.mid 0
```

`analyze-drums.js` reports, per GM percussion instrument, a 16-step bar grid plus a
verdict on whether hits land on the straight-16th grid or the triplet grid — turning
"does this groove swing?" into a measurement.

## Roadmap

- **MIR sidecar (`mir/`)** — Python: capture real audio (WASAPI loopback) →
  stem-separate (Demucs) → tempo/downbeats (madmom) → audio-to-MIDI (Spotify
  basic-pitch) → feed the existing `analyze-drums.js` / `tab2strudel.js` tools.
  Audio-to-MIDI closes the loop: any recording becomes verifiable groove data.

## Licensing notes

- This repo: **MIT** (see [LICENSE](LICENSE)).
- Strudel itself is AGPL-3.0; the `strudelvs` extension bundles that engine.
- **No copyrighted audio or MIDI is committed** — all media is gitignored.
