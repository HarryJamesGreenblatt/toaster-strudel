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

## Phase 2 — stem separation + per-register grids (works now)

```powershell
pip install -r requirements-optional.txt      # Demucs (pulls PyTorch)

# Split into drums/bass/other/vocals stems (soundfile output, no torchcodec)
python separate_stems.py path\to\clip.wav

# Isolate guira/congas/bombo by frequency band, with an accent-intensity grid
python analyze_audio.py "separated\htdemucs\<clip>\drums.wav" --bands
```

Band mode maps to cumbia percussion physics — güira in the highs, congas in the mids,
bombo in the lows — and reports an accent grid so a *continuous* scrape's dynamic
"chu-[dip]-chuchu" is visible (onset-counting alone saturates on a scraper).

## Harmonic analysis — key, bassline, chords (works now)

```powershell
python analyze_audio.py clip.wav --key                 # Krumhansl-Schmuckler key
python analyze_audio.py stems\bass.wav  --bassline     # pyin note-per-beat
python analyze_audio.py stems\other.wav --chords       # chord-per-bar (chroma templates)
python analyze_audio.py clip.wav --chords --per-beat   # chord-per-beat
```

Measure pitch, not just rhythm: rhythm accuracy alone won't match a recording if the
key/harmony are guessed. Feed the detected key + progression straight into `note(...)`,
`chord("<...>")`, and `.voicing()`.

## Roadmap

- **Phase 3 — audio → MIDI:** Spotify `basic-pitch` emits MIDI for melodic/bass
  lines that flows into `../mcp-server/src/analyze-drums.js` and `tab2strudel.js`.
  (basic-pitch is a *pitch* detector — use it for bass/accordion, not percussion.)

## Notes

- `.venv/` and all audio/MIDI are gitignored (see repo root `.gitignore`).
- Never commit copyrighted captures — the repo is public.
