"""
split_drums.py — separate a composite drum stem into per-instrument voices by
ONSET TIMBRE CLUSTERING (no extra model needed).

Frequency-band splitting fails because bands are not instruments — a kick and a conga
both put energy in the low band, so every voice fires on the same grid (jackhammer).
Instead: detect each hit, describe its timbre, and cluster hits so each onset belongs
to exactly ONE voice. Writes listenable per-voice WAVs (confirm by ear) and prints the
quantized pattern + a Strudel line per voice.

Usage:
    python split_drums.py <drums.wav> [--voices 4] [--bpm 97.5] [--grid 16] [--out drumvoices]
"""

import argparse
import os
import sys
from pathlib import Path

# KMeans on Windows can deadlock via OpenMP/MKL threading — force single-thread.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import librosa
import numpy as np
import soundfile as sf
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# per-voice Strudel sound by ascending brightness (spectral centroid)
VOICE_SOUNDS = ["bd", "lt", "mt", "hh", "cr"]
VOICE_NAMES = ["kick/bombo", "low conga/tom", "mid conga/timbal", "guira/hat", "cymbal"]


def onset_features(y: np.ndarray, sr: int, onsets: np.ndarray) -> np.ndarray:
    """Timbre feature vector per onset: centroid, bandwidth, rolloff, ZCR, flatness."""
    feats = []
    win = int(0.05 * sr)
    for ot in onsets:
        s = int(ot * sr)
        seg = y[s:s + win]
        if len(seg) < win // 2:
            seg = np.pad(seg, (0, win - len(seg)))
        S = np.abs(librosa.stft(seg, n_fft=1024, hop_length=256)) + 1e-9
        cent = librosa.feature.spectral_centroid(S=S, sr=sr).mean()
        bw = librosa.feature.spectral_bandwidth(S=S, sr=sr).mean()
        roll = librosa.feature.spectral_rolloff(S=S, sr=sr).mean()
        zcr = librosa.feature.zero_crossing_rate(seg).mean()
        flat = librosa.feature.spectral_flatness(S=S).mean()
        feats.append([cent, bw, roll, zcr, flat])
    return np.array(feats)


def fold_pattern(onsets_v: np.ndarray, t0: float, step: float, grid: int) -> tuple[str, str]:
    """Fold a voice's onsets onto one loop bar -> (struct, gain) strings."""
    acc = np.zeros(grid)
    cnt = np.zeros(grid)
    for ot in onsets_v:
        cell = int(round((ot - t0) / step))
        if cell < 0:
            continue
        acc[cell % grid] += 1.0
        cnt[cell % grid] += 1.0
    peak = acc.max() if acc.max() > 0 else 1.0
    struct = " ".join("x" if acc[i] > 0 else "~" for i in range(grid))
    gain = " ".join(f"{acc[i]/peak:.2f}" if acc[i] > 0 else "0" for i in range(grid))
    return struct, gain


def main() -> int:
    ap = argparse.ArgumentParser(description="Separate a drum stem into voices by onset timbre clustering.")
    ap.add_argument("drums")
    ap.add_argument("--voices", type=int, default=4)
    ap.add_argument("--bpm", type=float, default=None)
    ap.add_argument("--grid", type=int, default=16)
    ap.add_argument("--out", default="drumvoices")
    args = ap.parse_args()

    y, sr = librosa.load(args.drums, sr=None, mono=True)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True, units="time")
    if len(onsets) < args.voices:
        print("not enough onsets to cluster")
        return 1

    feats = onset_features(y, sr, onsets)
    X = StandardScaler().fit_transform(feats)
    km = KMeans(n_clusters=args.voices, n_init=10, random_state=0).fit(X)
    labels = km.labels_

    # order clusters by mean spectral centroid (feature 0) -> low..high
    order = np.argsort([feats[labels == k, 0].mean() for k in range(args.voices)])
    rank = {old: new for new, old in enumerate(order)}

    # grid anchor
    if args.bpm:
        bpm = args.bpm
        t0 = float(onsets[0])
    else:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        bpm = float(np.atleast_1d(tempo)[0])
        t0 = float(beats[0]) if len(beats) else float(onsets[0])
    step = (60.0 / bpm) / (args.grid / 4.0)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    win = int(0.14 * sr)
    fade = np.hanning(min(256, win) * 2)[: min(256, win)]

    print(f"bpm={bpm:.1f}  onsets={len(onsets)}  voices={args.voices}\n")
    for k in range(args.voices):
        v = rank[k]
        sel = onsets[labels == k]
        # write listenable per-voice audio
        buf = np.zeros(len(y), dtype=np.float32)
        for ot in sel:
            s = int(ot * sr)
            seg = y[s:s + win].copy()
            if len(seg) == 0:
                continue
            seg[: len(fade)] *= fade
            buf[s:s + len(seg)] += seg
        name = VOICE_NAMES[v] if v < len(VOICE_NAMES) else f"voice{v}"
        snd = VOICE_SOUNDS[v] if v < len(VOICE_SOUNDS) else "bd"
        path = out_dir / f"{v}_{snd}.wav"
        sf.write(str(path), buf, sr)

        struct, gain = fold_pattern(sel, t0, step, args.grid)
        cent = feats[labels == k, 0].mean()
        print(f"voice {v} [{name}]  hits={len(sel):>3}  centroid={cent:6.0f}Hz  -> {path.name}")
        print(f'  s("{snd}").struct("<[{struct}]>").gain("<[{gain}]>")')
    print(f"\nWrote {args.voices} listenable voice stems to {out_dir}/ — confirm each by ear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
