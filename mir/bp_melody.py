"""
bp_melody.py — POLYPHONIC melody transcription via Spotify basic-pitch (ONNX backend).

Unlike transcribe_stem.py --mode mono (pyin: one pitch/instant, octave errors, grid-
snap), basic-pitch is a real polyphonic note detector: it returns note events with
true onsets, durations, pitches and amplitude. This is the right tool for a melody
carried by a polyphonic instrument (accordion).

Usage:
    python bp_melody.py <stem.wav> --start 12.284 --bpm 97.5 --grid 16 [--mono] [--min-pitch 55]

--start should be a BASS BAR BOUNDARY (e.g. 12.284 = anchor 4.899 + 3 bars) so the
melody grid locks to the bass. --mono keeps the top (highest) note per cell.
"""

import argparse
import os
import sys
import tempfile

os.environ.setdefault("BASIC_PITCH_BACKEND", "onnx")

import librosa
import numpy as np
import soundfile as sf


def main() -> int:
    ap = argparse.ArgumentParser(description="Polyphonic melody transcription (basic-pitch, ONNX).")
    ap.add_argument("stem")
    ap.add_argument("--start", type=float, default=0.0, help="region start (s); use a bass bar boundary")
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--bpm", type=float, default=97.5)
    ap.add_argument("--grid", type=int, default=16)
    ap.add_argument("--mono", action="store_true", help="keep only the highest note per cell (melody line)")
    ap.add_argument("--min-pitch", type=int, default=0, help="drop notes below this MIDI number")
    ap.add_argument("--max-pitch", type=int, default=127, help="drop notes above this MIDI number")
    ap.add_argument("--min-dur", type=float, default=0.0, help="drop notes shorter than this (s) — filters arpeggio filler")
    ap.add_argument("--min-amp", type=float, default=0.0, help="drop notes quieter than this amplitude (0..1)")
    ap.add_argument("--hold", action="store_true", help="sustain each note for its duration (uses _) instead of one-cell hits")
    args = ap.parse_args()

    y, sr = librosa.load(args.stem, sr=None, mono=True)
    s = int(args.start * sr)
    e = int(args.end * sr) if args.end else len(y)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    sf.write(tmp, y[s:e], sr)

    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    _, _, notes = predict(tmp, model_or_model_path=ICASSP_2022_MODEL_PATH)
    os.unlink(tmp)

    # notes: (start_s, end_s, pitch_midi, amplitude, bends) — times relative to the trim
    step = (60.0 / args.bpm) / (args.grid / 4.0)
    events = []  # (onset_idx, pitch, amp, dur_cells)
    max_idx = 0
    for ev in notes:
        st, en, pitch, amp = ev[0], ev[1], int(ev[2]), float(ev[3])
        if pitch < args.min_pitch or pitch > args.max_pitch:
            continue
        dur = en - st
        if dur < args.min_dur or amp < args.min_amp:
            continue
        idx = int(round(st / step))  # --start is a bar boundary -> relative == grid-aligned
        if idx < 0:
            continue
        dcells = max(1, int(round(dur / step)))
        events.append((idx, pitch, amp, dcells))
        max_idx = max(max_idx, idx)

    total = ((max_idx // args.grid) + 1) * args.grid
    seq = ["~"] * total

    if args.mono:
        # one line: keep the top (highest) pitch at each onset cell
        by_cell: dict[int, tuple[int, int]] = {}
        for idx, pitch, amp, dcells in events:
            cur = by_cell.get(idx)
            if cur is None or pitch > cur[0]:
                by_cell[idx] = (pitch, dcells)
        onsets = sorted(by_cell)
        for i, idx in enumerate(onsets):
            pitch, dcells = by_cell[idx]
            seq[idx] = librosa.midi_to_note(pitch, unicode=False).lower().replace("♯", "#")
            if args.hold:
                nxt = onsets[i + 1] if i + 1 < len(onsets) else total
                for j in range(idx + 1, min(idx + dcells, nxt, total)):
                    seq[j] = "_"
    else:
        poly: dict[int, set[int]] = {}
        for idx, pitch, amp, dcells in events:
            poly.setdefault(idx, set()).add(pitch)
        for idx, pitches in poly.items():
            ps = sorted(pitches)
            names = ",".join(librosa.midi_to_note(p, unicode=False).lower().replace("♯", "#") for p in ps)
            seq[idx] = f"[{names}]" if len(ps) > 1 else names

    bars = [" ".join(seq[b:b + args.grid]) for b in range(0, total, args.grid)]
    mini = "<" + " ".join(f"[{b}]" for b in bars) + ">"
    print(f"kept notes={len(events)} (of {len(notes)})  ", end="")

    print(f"basic-pitch notes={len(notes)}  used bars={len(bars)}  grid={args.grid}\n")
    for i, b in enumerate(bars):
        print(f"  bar {i+1}: {b}")
    print(f'\nnote("{mini}")')
    return 0


if __name__ == "__main__":
    sys.exit(main())
