# mir — audio analysis sidecar

Python MIR (Music Information Retrieval) tools that turn **real audio** into
verifiable groove data for Strudel. Capture anything (WASAPI loopback in Audacity →
WAV), analyze the actual rhythm, and translate the measured pattern — no guessing.

## Setup

```powershell
cd mir
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Python **3.12** is what this targets. `madmom` is intentionally excluded (it does not
build on 3.12); beat tracking uses `librosa`.

## Phase 1 — tempo, beat, onset grid (works now)

```powershell
# Analyze a captured clip
python analyze_audio.py path\to\clip.wav

# Or verify the pipeline with a synthetic 90 BPM "X.XX" cumbia click
python analyze_audio.py --selftest
```

Reports the detected BPM (as `setcpm(bpm/4)`), a 16-step bar grid of onset density,
and a **straight-16th vs triplet** verdict — the audio-domain analogue of
`../mcp-server/src/analyze-drums.js`.

## Roadmap

- **Phase 2 — stems:** `pip install -r requirements-optional.txt` → run Demucs to
  split `drums/bass/other`, then analyze each stem separately for per-instrument grids.
- **Phase 3 — audio → MIDI:** Spotify `basic-pitch` emits MIDI that flows straight
  into `../mcp-server/src/analyze-drums.js` and `tab2strudel.js`.

## Notes

- `.venv/` and all audio/MIDI are gitignored (see repo root `.gitignore`).
- Never commit copyrighted captures — the repo is public.
