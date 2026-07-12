#!/usr/bin/env python
"""sampleize.py — chop an isolated voice into a clean, cycle-looping sample.

The 4th reproduction mode (sample). When a library sound is fake/tinny, use the
REAL isolated audio from the record. Takes a separated voice WAV, extracts a
bar-length clip at the measured tempo, and crossfades the seam so it loops
seamlessly over one cycle. Writes a listenable WAV.

COPYRIGHT: output is derived from copyrighted audio -> keep it LOCAL and gitignored;
serve it from a local server for strudel.cc, never commit or host publicly.

Usage:
  python sampleize.py <voice.wav> --bpm 97.5 [--bars 1] [--beats 4]
                      [--start 0] [--crossfade 0.02] [--gain 1.0]
                      [--out mir/samples/kual_guira_1bar.wav]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf


def main() -> int:
    ap = argparse.ArgumentParser(description="Chop an isolated voice into a seamless 1-bar loop.")
    ap.add_argument("wav", type=Path)
    ap.add_argument("--bpm", type=float, required=True)
    ap.add_argument("--bars", type=int, default=1)
    ap.add_argument("--beats", type=int, default=4, help="beats per bar")
    ap.add_argument("--start", type=float, default=0.0, help="start seconds (align to a downbeat)")
    ap.add_argument("--end", type=float, default=None, help="explicit end seconds (overrides --bars for the raw chop)")
    ap.add_argument("--fit-bars", type=int, default=None, help="pitch-preserving time-stretch the chop to exactly N bars")
    ap.add_argument("--crossfade", type=float, default=0.02, help="loop-seam crossfade seconds")
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    if not args.wav.exists():
        print(f"error: no such file: {args.wav}")
        return 2

    y, sr = librosa.load(str(args.wav), sr=None, mono=True)
    bar_sec = args.beats * (60.0 / args.bpm)  # seconds per bar
    xf = max(0, int(round(args.crossfade * sr)))
    start = int(round(args.start * sr))

    # raw region: explicit --end wins, else --bars from start
    if args.end is not None:
        end = int(round(args.end * sr))
    else:
        end = start + int(round(args.bars * bar_sec * sr))
    if end + xf > len(y):
        y = np.pad(y, (0, end + xf - len(y)))
    region = y[start:end + xf].astype(np.float64).copy()

    # pitch-preserving stretch to exactly fit_bars (phase vocoder)
    if args.fit_bars:
        target = int(round(args.fit_bars * bar_sec * sr)) + xf
        rate = len(region) / max(1, target)
        region = librosa.effects.time_stretch(region.astype(np.float32), rate=rate).astype(np.float64)

    core = max(1, len(region) - xf)
    if xf > 0 and len(region) >= 2 * xf:
        fade = np.linspace(0.0, 1.0, xf)
        head = region[:xf].copy()
        tail = region[core:core + xf].copy()
        loop = region[:core].copy()
        loop[:xf] = head * fade + tail * (1.0 - fade)
    else:
        loop = region[:core].copy()

    peak = float(np.max(np.abs(loop))) or 1.0
    loop = (loop / peak) * args.gain * 0.98

    out = args.out or (Path("mir/samples") / (args.wav.stem + "_loop.wav"))
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), loop.astype(np.float32), sr)
    nbars = args.fit_bars or args.bars
    print(f"wrote {out}  ({len(loop) / sr:.3f}s, ~{nbars} bars, {len(loop)} samples @ {sr}Hz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
