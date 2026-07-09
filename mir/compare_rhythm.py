"""
compare_rhythm.py — compare a reference recording against a Strudel render.

Reports per-band accent-grid similarity so we can iterate on rhythmic signatures
objectively instead of eyeballing strings.

Usage:
    python compare_rhythm.py reference.wav render.wav
"""

import argparse
import sys

import librosa
import numpy as np

from analyze_audio import BANDS, accent_grid, bandpass, render_levels


def corr(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def marks(a: np.ndarray, b: np.ndarray) -> str:
    """Mark large mismatches between two normalized accent grids."""
    d = np.abs(a - b)
    return "".join("!" if x >= 0.35 else ("^" if x >= 0.22 else ".") for x in d)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare rhythm/accent signatures between two audio files.")
    ap.add_argument("reference")
    ap.add_argument("render")
    args = ap.parse_args()

    y_ref, sr_ref = librosa.load(args.reference, sr=None, mono=True)
    y_out, sr_out = librosa.load(args.render, sr=sr_ref, mono=True)

    tempo_ref, _ = librosa.beat.beat_track(y=y_ref, sr=sr_ref, units="frames")
    tempo_out, _ = librosa.beat.beat_track(y=y_out, sr=sr_ref, units="frames")
    tempo_ref = float(np.atleast_1d(tempo_ref)[0])
    tempo_out = float(np.atleast_1d(tempo_out)[0])

    print(f"reference bpm={tempo_ref:.1f}   render bpm={tempo_out:.1f}")
    print("metric: corr closer to 1 is better; mae closer to 0 is better")
    print("marks: !=large mismatch, ^=medium mismatch, .=close\n")

    for label, (lo, hi) in BANDS.items():
        ref = accent_grid(bandpass(y_ref, sr_ref, lo, hi), sr_ref, tempo_ref)
        out = accent_grid(bandpass(y_out, sr_ref, lo, hi), sr_ref, tempo_out)
        print(label)
        print(f"  ref |{render_levels(ref)}|")
        print(f"  out |{render_levels(out)}|")
        print(f"  dif |{marks(ref, out)}|  corr={corr(ref, out):.3f}  mae={mae(ref, out):.3f}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
