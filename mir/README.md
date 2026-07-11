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

## Second pass — per-stem transcription (works now)

The analyses above *summarize* a stem. To actually reproduce it, transcribe each
isolated stem into discrete note/onset events quantized to a grid:

```powershell
# Monophonic (bass, lead): onset + per-onset pitch -> note("<[bar] ...>")
python transcribe_stem.py stems\bass.wav  --mode mono --bpm 97.5 --grid 16 --bars 8

# Unpitched (drum stem): onset + velocity -> s(sound).struct(...).gain(...)
python transcribe_stem.py stems\drums.wav --mode perc --bpm 97.5 --grid 16 --bars 8
```

This is what `--bassline` (one median pitch per beat) could not do: it recovers the
real sub-beat rhythm and note changes — e.g. the cumbia bass's `f2 ~ ~ ~ c2 ~ c3 ~`
octave pump, which the per-beat median flattened to a single `f2`.

Polyphonic stems (accordion in `other`) need multi-pitch transcription — a future
`basic-pitch` add. `mono` handles single-line parts well today.

## Second pass, stage 2 — sub-separate a lumped stem (works now)

htdemucs 4-stem lumps **every** synth (pads, strings, lead, orchestra hits) into the
single `other` stem. Transcribing `other` directly feeds basic-pitch a multi-instrument
soup → noise. `subseparate.py` splits ONE stem into instrument voices *before*
transcribing:

```powershell
# HPSS: sustained pads (harmonic) vs. orch-hit stabs (percussive), + optional NMF
python subseparate.py "separated\htdemucs\<clip>\other.wav" --margin 4 --voices 2
```

- **HPSS** writes `harmonic.wav` (pads/strings/sustained lead) and `percussive.wav`
  (attack-heavy stabs). **NMF** (`--voices K --target harmonic|percussive|both`) factors
  a part further into Wiener-masked spectral voices.
- Every output is a listenable WAV; the tool reports spectral centroid, energy share and
  onset count per voice so you can identify each, then transcribe it in isolation.
- **Caveat learned:** this only works when the instruments differ in the HPSS/spectral
  sense. On a pad-drenched, tonal track (Moments in Love) the `other` stem measured
  **~95% sustained harmonic energy** and the *tonal* orch hits would not separate as
  "percussive" — so no clean orch-hit layer exists to pull out. When a song is dominated
  by overlapping sustained synths, prefer a real **MIDI multitrack** (`tab2strudel
  --fetch`) where each instrument is already its own clean track.


## Drum-voice separation (works now)

A single Demucs `drums` stem is a dense ensemble; frequency-band splitting is NOT
instrument separation (a kick and a conga both hit the low band → every voice fires on
the same grid = jackhammer). Two real approaches:

```powershell
pip install -r requirements-optional.txt   # adds scikit-learn

# Onset timbre clustering — assigns each HIT to one voice (bleeds on overlaps)
python split_drums.py "separated\htdemucs\<clip>\drums.wav" --voices 4 --bpm 97.5

# NMF spectral factorization — handles OVERLAP, soft-mask reconstruction (cleaner)
python nmf_drums.py   "separated\htdemucs\<clip>\drums.wav" --voices 4 --bpm 97.5
```

Both write **listenable per-voice WAVs** (`drumvoices/` and `drumnmf/`) so you confirm
each channel by ear, plus a folded `struct`/`gain` per voice. Prefer **NMF** — it
factors the spectrogram into templates × activations, so overlapping hits are decomposed
rather than duplicated. Note: centroid order ≠ instrument identity — always audition.

For splitting the composite `other` stem (accordion/guitar/piano), use the 6-source model:

```powershell
python separate_stems.py clip.wav --model htdemucs_6s   # adds guitar + piano stems
```

## Roadmap

- **Phase 3 — audio → MIDI:** Spotify `basic-pitch` emits MIDI for melodic/bass
  lines that flows into `../mcp-server/src/analyze-drums.js` and `tab2strudel.js`.
  (basic-pitch is a *pitch* detector — use it for bass/accordion, not percussion.)

## Notes

- `.venv/` and all audio/MIDI are gitignored (see repo root `.gitignore`).
- Never commit copyrighted captures — the repo is public.
