"""
nmf_drums.py — separate a composite drum stem into voices by NMF (spectral
factorization), which handles OVERLAPPING hits that onset-clustering cannot.

Onset timbre-clustering (split_drums.py) assigns each ONSET to one voice, but it can't
un-mix simultaneous hits, and window-copy reconstruction bleeds the full mix into every
voice. NMF factors the magnitude spectrogram S ~= W @ H into K spectral templates (W)
and their activations (H). Each template is a voice (sort by centroid -> bombo..guira);
each activation is that voice's rhythm. Soft (Wiener) masks reconstruct clean per-voice
audio you can confirm by ear.

Usage:
    python nmf_drums.py <drums.wav> [--voices 4] [--bpm 97.5] [--grid 16] [--out drumnmf]
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")  # avoid sklearn/OpenMP deadlock on Windows

import librosa
import numpy as np
import soundfile as sf

VOICE_SOUNDS = ["bd", "lt", "mt", "hh", "cr", "rim"]
VOICE_NAMES = ["kick/bombo", "low conga", "mid conga/timbal", "guira/hat", "cymbal", "click"]

N_FFT = 2048
HOP = 512


def fold(onsets: np.ndarray, t0: float, step: float, grid: int) -> tuple[str, str]:
    acc = np.zeros(grid)
    for ot in onsets:
        cell = int(round((ot - t0) / step))
        if cell >= 0:
            acc[cell % grid] += 1.0
    peak = acc.max() if acc.max() > 0 else 1.0
    struct = " ".join("x" if acc[i] > 0 else "~" for i in range(grid))
    gain = " ".join(f"{acc[i] / peak:.2f}" if acc[i] > 0 else "0" for i in range(grid))
    return struct, gain


def main() -> int:
    ap = argparse.ArgumentParser(description="NMF drum-voice separation (handles overlap).")
    ap.add_argument("drums")
    ap.add_argument("--voices", type=int, default=4)
    ap.add_argument("--bpm", type=float, default=None)
    ap.add_argument("--grid", type=int, default=16)
    ap.add_argument("--out", default="drumnmf")
    args = ap.parse_args()

    y, sr = librosa.load(args.drums, sr=None, mono=True)
    S = librosa.stft(y, n_fft=N_FFT, hop_length=HOP)
    mag, phase = np.abs(S), np.angle(S)

    # NMF: mag ~= W (freq x K) @ H (K x frames)
    W, H = librosa.decompose.decompose(mag, n_components=args.voices, sort=True, random_state=0)

    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    centroids = [float((W[:, k] * freqs).sum() / (W[:, k].sum() + 1e-9)) for k in range(args.voices)]
    order = list(np.argsort(centroids))  # ascending centroid -> bombo..guira

    # grid anchor
    if args.bpm:
        bpm = args.bpm
        onset_all = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True, units="time")
        t0 = float(onset_all[0]) if len(onset_all) else 0.0
    else:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        bpm = float(np.atleast_1d(tempo)[0])
        t0 = float(beats[0]) if len(beats) else 0.0
    step = (60.0 / bpm) / (args.grid / 4.0)

    total = (W @ H) + 1e-9
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"bpm={bpm:.1f}  voices={args.voices}  (NMF spectral separation)\n")
    for rank, k in enumerate(order):
        snd = VOICE_SOUNDS[rank] if rank < len(VOICE_SOUNDS) else "bd"
        name = VOICE_NAMES[rank] if rank < len(VOICE_NAMES) else f"voice{rank}"

        # soft (Wiener) mask reconstruction of this component
        comp = np.outer(W[:, k], H[k])
        mask = comp / total
        yk = librosa.istft(mask * mag * np.exp(1j * phase), hop_length=HOP, length=len(y))
        sf.write(str(out_dir / f"{rank}_{snd}.wav"), yk.astype(np.float32), sr)

        # rhythm from the component's activation envelope
        env = H[k] / (H[k].max() + 1e-9)
        onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=HOP,
                                            backtrack=True, units="time")
        struct, gain = fold(onsets, t0, step, args.grid)
        print(f"voice {rank} [{name}]  centroid={centroids[k]:6.0f}Hz  hits={len(onsets):>3}  -> {rank}_{snd}.wav")
        print(f'  s("{snd}").struct("<[{struct}]>").gain("<[{gain}]>")')

    print(f"\nWrote {args.voices} soft-masked voice stems to {out_dir}/ — confirm each by ear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
