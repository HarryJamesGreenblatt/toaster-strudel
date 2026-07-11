# toaster-strudel

<table>
<tr>
<td width="50%">
<img src="assets/images/toaster-strudel-cover.png" alt="Toaster Strudel — AI music, together. A conductor pastry mascot beside a toaster pastry iced with a musical note." width="100%">
</td>
<td width="50%" valign="middle">

$$
\begin{aligned}
&\LARGE\textsf{Tools and knowledge for} \\
&\LARGE\textbf{\textsf{AI-assisted Strudel composition}} \\
&\large\textit{\textcolor{gray}{grounded in the real Strudel API, and in}} \\
&\large\textit{\textcolor{gray}{the actual rhythms of real music}} \\
&\large\textit{\textcolor{gray}{rather than guesswork.}}
\end{aligned}
$$

<div align="right"><sub>Strudel: <a href="https://strudel.cc">https://strudel.cc</a></sub></div>

</td>
</tr>
</table>

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

- **Host:** [strudel.cc](https://strudel.cc) itself — the real, continuously-updated
  Strudel app, with its own docs, autocomplete, sound banks, and file IO. It is the
  single source of truth for playback and timbre.
- **Compose:** edit `.strudel.js` files with normal editor tools.
- **Play & verify:** the assistant drives strudel.cc directly via browser automation
  — loads the active file into the real editor, presses play, reads back any error,
  and screenshots the pianoroll — so what you hear is exactly the live engine, with no
  copy-paste and no third-party reimplementation in between.
- **Ground:** consult the `strudel_docs` MCP tool for the real API before writing.
- **Verify groove:** analyze real performances to learn a genre's rhythmic nuance
  instead of guessing (see `mcp-server/src/analyze-drums.js`).

> **Why not the VS Code Strudel extension?** It bundles its *own* frozen copy of the
> engine and a different set of sample packs, so the same code can play on strudel.cc
> yet stay silent — or sound different — in the extension. We standardize on the real
> app to keep playback trustworthy and reproducible.

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

- **MIR sidecar (`mir/`)** — Python audio analysis. Capture real audio (WASAPI
  loopback) and measure the groove:
  - **Phase 1 (done):** tempo → `setcpm(bpm/4)`, onset grid + straight/triplet feel.
  - **Phase 2 (done):** Demucs stem separation, then per-register band analysis
    (low/mid/high) with an accent-intensity grid — isolates güira vs congas vs bombo.
  - **Phase 3 (next):** Spotify `basic-pitch` audio→MIDI for melodic/bass lines,
    feeding the existing `analyze-drums.js` / `tab2strudel.js` tools.

## Licensing notes

- This repo: **MIT** (see [LICENSE](LICENSE)).
- Strudel itself is AGPL-3.0; the `strudelvs` extension bundles that engine.
- **No copyrighted audio or MIDI is committed** — all media is gitignored.
