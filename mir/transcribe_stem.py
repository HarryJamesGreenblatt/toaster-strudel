"""
transcribe_stem.py — SECOND PASS: transcribe an isolated Demucs stem into discrete
note/onset events and emit Strudel mini-notation.

The first pass (analyze_audio.py) SUMMARIZES a stem (tempo, key, accent contour, chord
labels). This second pass actually TRANSCRIBES it: onset detection + per-onset pitch,
quantized to a grid, so the output is faithful mini-notation with real sub-beat rhythm
and note changes — not one-note-per-beat.

Usage:
    python transcribe_stem.py <stem.wav> --mode mono [--bpm 97.5] [--grid 16] [--bars 4]
    python transcribe_stem.py <stem.wav> --mode perc [--bpm 97.5] [--grid 16] [--bars 4]

  mono : monophonic pitch (bass, lead) -> note("<[bar] [bar] ...>")
  perc : unpitched hits (drum stem) -> s(sound) with a velocity/gain grid
"""

import argparse
import sys

import librosa
import numpy as np


def _note(hz: float) -> str:
    return librosa.hz_to_note(hz, unicode=False).lower().replace("♯", "#")


def _grid_anchor(y: np.ndarray, sr: int, bpm: float | None) -> tuple[float, float]:
    """Return (bpm, t0) where t0 is a downbeat/phase anchor for the grid."""
    if bpm is None:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        bpm = float(np.atleast_1d(tempo)[0])
        t0 = float(beats[0]) if len(beats) else 0.0
    else:
        onsets = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True, units="time")
        t0 = float(onsets[0]) if len(onsets) else 0.0
    return bpm, t0


def transcribe_mono(y: np.ndarray, sr: int, bpm: float | None, grid: int, bars: int | None) -> dict:
    bpm, t0 = _grid_anchor(y, sr, bpm)
    step = (60.0 / bpm) / (grid / 4.0)  # seconds per grid cell (grid cells per bar)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True, units="time")
    f0, voiced, _ = librosa.pyin(y, fmin=40.0, fmax=1000.0, sr=sr)
    tt = librosa.times_like(f0, sr=sr)

    dur = librosa.get_duration(y=y, sr=sr)
    total = bars * grid if bars else int(np.ceil((dur - t0) / step))
    cells = ["~"] * max(total, 0)
    events = []
    for ot in onsets:
        idx = int(round((ot - t0) / step))
        if idx < 0 or idx >= total:
            continue
        # sample pitch just after the attack transient
        w = (tt >= ot + 0.02) & (tt <= ot + 0.09) & voiced & np.isfinite(f0)
        if not np.any(w):
            continue
        note = _note(float(np.median(f0[w])))
        cells[idx] = note
        events.append((round(float(ot), 3), idx, note))

    bars_out = [" ".join(cells[b:b + grid]) for b in range(0, total, grid)]
    mini = "<" + " ".join(f"[{b}]" for b in bars_out) + ">"
    return {"bpm": round(bpm, 1), "grid": grid, "events": events, "bars": bars_out, "mini": mini}


def transcribe_perc(y: np.ndarray, sr: int, bpm: float | None, grid: int, bars: int | None) -> dict:
    bpm, t0 = _grid_anchor(y, sr, bpm)
    step = (60.0 / bpm) / (grid / 4.0)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True, units="time")
    env = librosa.onset.onset_strength(y=y, sr=sr)
    et = librosa.times_like(env, sr=sr)

    dur = librosa.get_duration(y=y, sr=sr)
    total = bars * grid if bars else int(np.ceil((dur - t0) / step))
    hits = [0.0] * max(total, 0)
    for ot in onsets:
        idx = int(round((ot - t0) / step))
        if 0 <= idx < total:
            j = int(np.argmin(np.abs(et - ot)))
            hits[idx] = max(hits[idx], float(env[j]))
    peak = max(hits) if hits and max(hits) > 0 else 1.0
    struct = "".join("x" if h > 0 else "~" for h in hits)  # placeholder, split below
    struct_cells = ["x" if h > 0 else "~" for h in hits]
    gain_cells = [f"{(h / peak):.2f}" if h > 0 else "0" for h in hits]

    bars_struct = [" ".join(struct_cells[b:b + grid]) for b in range(0, total, grid)]
    bars_gain = [" ".join(gain_cells[b:b + grid]) for b in range(0, total, grid)]
    return {
        "bpm": round(bpm, 1),
        "grid": grid,
        "struct": "<" + " ".join(f"[{b}]" for b in bars_struct) + ">",
        "gain": "<" + " ".join(f"[{b}]" for b in bars_gain) + ">",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Second-pass stem transcription -> Strudel mini-notation.")
    ap.add_argument("stem")
    ap.add_argument("--mode", choices=["mono", "perc"], default="mono")
    ap.add_argument("--bpm", type=float, default=None, help="known BPM (aligns the grid; else auto)")
    ap.add_argument("--grid", type=int, default=16, help="grid cells per bar (16 = 16ths)")
    ap.add_argument("--bars", type=int, default=None, help="how many bars to emit (default: whole clip)")
    args = ap.parse_args()

    y, sr = librosa.load(args.stem, sr=None, mono=True)

    if args.mode == "mono":
        r = transcribe_mono(y, sr, args.bpm, args.grid, args.bars)
        print(f"bpm={r['bpm']}  grid={r['grid']}  events={len(r['events'])}")
        print("\nfirst bars (one per line):")
        for i, b in enumerate(r["bars"][:8]):
            print(f"  bar {i+1}: {b}")
        print("\nStrudel:")
        print(f'  note("{r["mini"]}").s("gm_synth_bass_2")')
    else:
        r = transcribe_perc(y, sr, args.bpm, args.grid, args.bars)
        print(f"bpm={r['bpm']}  grid={r['grid']}")
        print("\nStrudel:")
        print(f'  s("bd").struct("{r["struct"]}").gain("{r["gain"]}")')
    return 0


if __name__ == "__main__":
    sys.exit(main())
