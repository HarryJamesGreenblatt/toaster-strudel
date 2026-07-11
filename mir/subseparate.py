r"""
subseparate.py — the MISSING second-pass stage: sub-separate ONE Demucs stem into its
constituent instrument voices before transcribing.

The problem this fixes: htdemucs 4-stem lumps EVERY synth — pads, strings, lead, AND the
orchestra-hit stabs — into a single `other` stem. Transcribing `other` directly feeds
basic-pitch a 4-instrument polyphonic soup, which comes out as noise. We separated the
MIX into stems but never separated the STEM into instruments.

Two complementary sub-separators (same idea as nmf_drums.py, generalized to melodic
content):

  1. HPSS (harmonic-percussive source separation). Sustained pads/strings are HARMONIC
     (stable partials, no attack); orchestra hits are PERCUSSIVE (sharp broadband
     attack). librosa.effects.hpss splits them cleanly — so `percussive.wav` isolates
     the orch-hit stabs (the HOOK) away from the pad wash in `harmonic.wav`.

  2. NMF (optional, --voices K). Factor the target's magnitude spectrogram S ~= W @ H
     into K spectral templates (voices) with Wiener-masked reconstruction — to split the
     harmonic part further into pad vs. lead when HPSS alone isn't enough.

Every output is written as a listenable WAV so you CONFIRM each voice by ear (then
transcribe it in isolation with bp_melody.py / transcribe_stem.py). Reports spectral
centroid, energy share, and onset count per voice to help identify them.

Usage:
    python subseparate.py "separated\htdemucs\<clip>\other.wav" --margin 3
    python subseparate.py stem.wav --voices 3 --target harmonic --out subsep
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")  # avoid sklearn/OpenMP deadlock on Windows

import librosa
import numpy as np
import soundfile as sf

N_FFT = 2048
HOP = 512


def describe(y: np.ndarray, sr: int, total_energy: float) -> str:
    """One-line spectral fingerprint of a separated voice for ear-free identification."""
    rms = float(np.sqrt(np.mean(y**2)) + 1e-12)
    share = 100.0 * float(np.sum(y**2)) / (total_energy + 1e-12)
    if rms > 1e-6:
        cen = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    else:
        cen = 0.0
    onsets = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True, units="time")
    return f"centroid={cen:6.0f}Hz  energy={share:4.1f}%  onsets={len(onsets):>3}", len(onsets)


def nmf_voices(y: np.ndarray, sr: int, k: int, out_dir: Path, prefix: str, total_energy: float):
    """Factor y into K Wiener-masked spectral voices, sorted low->high centroid."""
    S = librosa.stft(y, n_fft=N_FFT, hop_length=HOP)
    mag, phase = np.abs(S), np.angle(S)
    W, H = librosa.decompose.decompose(mag, n_components=k, sort=True, random_state=0)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    centroids = [float((W[:, j] * freqs).sum() / (W[:, j].sum() + 1e-9)) for j in range(k)]
    order = list(np.argsort(centroids))
    total = (W @ H) + 1e-9
    for rank, j in enumerate(order):
        comp = np.outer(W[:, j], H[j])
        yk = librosa.istft((comp / total) * mag * np.exp(1j * phase), hop_length=HOP, length=len(y))
        path = out_dir / f"{prefix}_voice{rank}.wav"
        sf.write(str(path), yk.astype(np.float32), sr)
        info, _ = describe(yk, sr, total_energy)
        print(f"    {prefix} voice{rank}:  {info}  -> {path.name}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sub-separate a stem into instrument voices (HPSS + NMF).")
    ap.add_argument("stem", help="path to a single Demucs stem (e.g. other.wav)")
    ap.add_argument("--out", default=None, help="output dir (default: <stem_dir>/subsep)")
    ap.add_argument("--margin", type=float, default=3.0,
                    help="HPSS separation margin (>1 = stricter/cleaner split; try 2-8)")
    ap.add_argument("--voices", type=int, default=0,
                    help="if >0, NMF the --target into this many spectral voices")
    ap.add_argument("--target", choices=["harmonic", "percussive", "both"], default="harmonic",
                    help="which HPSS part to NMF-split further (default harmonic)")
    args = ap.parse_args()

    y, sr = librosa.load(args.stem, sr=None, mono=True)
    total_energy = float(np.sum(y**2))
    out_dir = Path(args.out) if args.out else Path(args.stem).parent / "subsep"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) HPSS: harmonic (pads/strings/lead) vs percussive (orch-hit stabs)
    y_h, y_p = librosa.effects.hpss(y, margin=(args.margin, args.margin))
    sf.write(str(out_dir / "harmonic.wav"), y_h.astype(np.float32), sr)
    sf.write(str(out_dir / "percussive.wav"), y_p.astype(np.float32), sr)

    print(f"HPSS margin={args.margin}  ->  {out_dir}/\n")
    hi, _ = describe(y_h, sr, total_energy)
    pi, _ = describe(y_p, sr, total_energy)
    print(f"  harmonic   (pads/strings/sustained lead):  {hi}  -> harmonic.wav")
    print(f"  percussive (orch-hit stabs / attacks):     {pi}  -> percussive.wav")

    # 2) optional NMF sub-split of the chosen part(s)
    if args.voices > 0:
        print(f"\n  NMF split into {args.voices} voices (target={args.target}):")
        if args.target in ("harmonic", "both"):
            nmf_voices(y_h, sr, args.voices, out_dir, "harm", total_energy)
        if args.target in ("percussive", "both"):
            nmf_voices(y_p, sr, args.voices, out_dir, "perc", total_energy)

    print("\nNext: audition each WAV, then transcribe the isolated voice, e.g.")
    print(f'  python bp_melody.py "{out_dir / "percussive.wav"}" --start <s> --bpm <bpm> --mono')
    print(f'  python transcribe_stem.py "{out_dir / "harmonic.wav"}" --mode chord --bpm <bpm>')
    return 0


if __name__ == "__main__":
    sys.exit(main())
