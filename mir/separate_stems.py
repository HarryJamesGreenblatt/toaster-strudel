"""
separate_stems.py — split an audio file into Demucs stems (drums/bass/other/vocals).

Uses the Demucs Python API and writes WAVs with soundfile, bypassing torchaudio's
newer torchcodec save path (which needs FFmpeg libs on Windows). Output stems feed
analyze_audio.py for per-instrument rhythm analysis.

Usage:
    python separate_stems.py <clip.wav> [--out separated] [--model htdemucs]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def main() -> int:
    ap = argparse.ArgumentParser(description="Demucs stem separation (soundfile output).")
    ap.add_argument("audio", help="path to input audio")
    ap.add_argument("--out", default="separated", help="output directory")
    ap.add_argument("--model", default="htdemucs", help="Demucs model name")
    args = ap.parse_args()

    import torch
    import librosa
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    model = get_model(args.model)
    model.eval()
    sr = model.samplerate          # 44100
    ch = model.audio_channels      # 2

    # load at the model's native rate, forced to stereo (channels, samples)
    wav, _ = librosa.load(args.audio, sr=sr, mono=False)
    wav = np.atleast_2d(wav)
    if wav.shape[0] == 1:
        wav = np.repeat(wav, ch, axis=0)
    x = torch.tensor(wav, dtype=torch.float32)

    # Demucs' normalization (mean/std over the mixed reference)
    ref = x.mean(0)
    x = (x - ref.mean()) / (ref.std() + 1e-8)

    print(f"model={args.model}  sources={model.sources}  sr={sr}")
    print("separating (CPU)... this takes a few minutes")
    with torch.no_grad():
        sources = apply_model(model, x[None], device="cpu", progress=True)[0]
    sources = sources * ref.std() + ref.mean()

    stem = Path(args.audio).stem
    out_dir = Path(args.out) / args.model / stem
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, source in zip(model.sources, sources):
        path = out_dir / f"{name}.wav"
        sf.write(str(path), source.T.numpy(), sr)  # (samples, channels)
        print(f"  wrote {path}")

    print(f"\nDone. Analyze a stem with:\n  python analyze_audio.py \"{out_dir / 'drums.wav'}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
