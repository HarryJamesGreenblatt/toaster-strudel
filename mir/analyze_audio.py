"""
analyze_audio.py — extract rhythmic structure from an audio clip for strudelization.

Phase 1 of the MIR sidecar: given a WAV (e.g. captured via WASAPI loopback in
Audacity), report tempo -> setcpm(bpm/4), and fold detected onsets into a 16-step
bar grid with a straight-16th vs triplet verdict — the audio-domain analogue of
../mcp-server/src/analyze-drums.js.

Usage:
    python analyze_audio.py <clip.wav> [--bars 4] [--json]
    python analyze_audio.py --selftest        # synthesize a 90 BPM test clip & analyze
"""

import argparse
import json
import sys

import numpy as np


def classify_phase(phase: float) -> tuple[float, float]:
    """Distance of a beat-phase (0..1) to the nearest straight-16th vs triplet grid."""
    straight = [0.0, 0.25, 0.5, 0.75]
    triplet = [0.0, 1 / 3, 2 / 3]
    near = lambda grid: min([abs(phase - p) for p in grid] + [abs(phase - 1.0)])
    return near(straight), near(triplet)


# Frequency bands mapped to cumbia percussion physics
BANDS = {
    "low  (bombo/kick)": (20, 200),
    "mid  (congas/timbal)": (200, 2000),
    "high (guira/hats)": (2000, 16000),
}


def bandpass(y: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    """4th-order Butterworth bandpass (zero-phase) to isolate a percussion register."""
    from scipy.signal import butter, sosfiltfilt

    nyq = sr / 2.0
    hi = min(hi, nyq * 0.99)
    sos = butter(4, [lo / nyq, hi / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, y).astype(np.float32)


def accent_grid(y: np.ndarray, sr: int, tempo: float, steps: int = 16) -> np.ndarray:
    """Average onset-strength per 16th-step of the bar (0..1). Reveals ACCENTS in a
    continuous scrape where onset-counting saturates."""
    import librosa

    env = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.times_like(env, sr=sr, hop_length=512)
    beat_sec = 60.0 / tempo if tempo > 0 else 0.0
    if beat_sec <= 0:
        return np.zeros(steps)
    acc = np.zeros(steps)
    cnt = np.zeros(steps)
    for t, e in zip(times, env):
        idx = int(((t / (beat_sec * 4)) % 1.0) * steps) % steps
        acc[idx] += e
        cnt[idx] += 1
    acc = acc / np.maximum(cnt, 1)
    peak = acc.max()
    return acc / peak if peak > 0 else acc


def render_levels(values: np.ndarray) -> str:
    """Render a 0..1 array as a heat bar so accent contours are visible."""
    ramp = " .:-=+*#%@"
    return "".join(ramp[min(len(ramp) - 1, int(v * (len(ramp) - 1) + 0.5))] for v in values)


# Krumhansl-Schmuckler key profiles
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def estimate_key(y: np.ndarray, sr: int) -> dict:
    """Estimate musical key via chroma correlation with Krumhansl-Schmuckler profiles."""
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    chroma = chroma / (chroma.sum() + 1e-9)
    best = None
    for i in range(12):
        maj = np.corrcoef(chroma, np.roll(_KS_MAJOR, i))[0, 1]
        minr = np.corrcoef(chroma, np.roll(_KS_MINOR, i))[0, 1]
        for mode, score in (("major", maj), ("minor", minr)):
            if best is None or score > best[2]:
                best = (_PITCHES[i], mode, score)
    tonic, mode, score = best
    return {"key": f"{tonic} {mode}", "tonic": tonic, "mode": mode, "confidence": round(float(score), 3)}


def _hz_to_note(hz: float) -> str:
    import librosa

    return librosa.hz_to_note(hz, unicode=False).lower().replace("♯", "#")


def extract_bassline(y: np.ndarray, sr: int) -> dict:
    """Monophonic pitch-track the bass stem (pyin), report the note per beat."""
    import librosa

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    f0, voiced, _ = librosa.pyin(y, fmin=40.0, fmax=400.0, sr=sr)
    t = librosa.times_like(f0, sr=sr)

    notes = []
    for i in range(len(beat_times) - 1):
        lo, hi = beat_times[i], beat_times[i + 1]
        mask = (t >= lo) & (t < hi) & voiced & np.isfinite(f0)
        vals = f0[mask]
        notes.append(_hz_to_note(float(np.median(vals))) if len(vals) else "~")
    return {"bpm": round(tempo, 1), "beats": len(beat_times), "notes_per_beat": notes}


# Chord templates (pitch-class intervals from the root)
_CHORD_TEMPLATES = {
    "": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10], "sus4": [0, 5, 7], "dim": [0, 3, 6],
}


def _template_vec(intervals: list[int]) -> np.ndarray:
    v = np.zeros(12)
    for i in intervals:
        v[i % 12] = 1.0
    return v


def chord_progression(y: np.ndarray, sr: int, per_bar: bool = True) -> dict:
    """Beat-synchronous chroma -> chord labels via template matching."""
    import librosa

    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, trim=False)
    tempo = float(np.atleast_1d(tempo)[0])
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    beat_chroma = librosa.util.sync(chroma, beats, aggregate=np.median)

    templates = []
    for root in range(12):
        for name, iv in _CHORD_TEMPLATES.items():
            t = np.roll(_template_vec(iv), root)
            templates.append((_PITCHES[root] + name, t / (np.linalg.norm(t) + 1e-9)))

    cols = beat_chroma.shape[1]
    step = 4 if per_bar else 1
    labels = []
    for start in range(0, cols, step):
        seg = beat_chroma[:, start:start + step].mean(axis=1)
        seg = seg / (np.linalg.norm(seg) + 1e-9)
        best = max(templates, key=lambda kt: float(np.dot(seg, kt[1])))
        labels.append(best[0])
    return {"bpm": round(tempo, 1), "unit": "bar" if per_bar else "beat", "chords": labels}


def analyze(y: np.ndarray, sr: int, bars: int = 4, fixed_tempo: float | None = None) -> dict:
    import librosa

    # tempo + beat grid (or reuse a shared tempo when analyzing bands)
    if fixed_tempo is None:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        tempo = float(np.atleast_1d(tempo)[0])
    else:
        tempo = fixed_tempo
        beat_frames = []

    # onsets (times in seconds)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    # beat period from tempo; fold each onset into its phase within a beat
    beat_sec = 60.0 / tempo if tempo > 0 else 0.0
    grid = [0] * 16
    straight_err = triplet_err = 0.0
    counted = 0
    if beat_sec > 0:
        for t in onset_times:
            beat_pos = (t / beat_sec) % 1.0          # phase within the beat (0..1)
            bar_pos = (t / (beat_sec * 4)) % 1.0     # phase within a 4/4 bar (0..1)
            grid[int(round(bar_pos * 16)) % 16] += 1
            se, te = classify_phase(beat_pos)
            straight_err += se
            triplet_err += te
            counted += 1

    if counted:
        straight_err /= counted
        triplet_err /= counted
        if triplet_err < straight_err * 0.8:
            verdict = "TRIPLET/swung"
        elif straight_err < triplet_err * 0.8:
            verdict = "straight"
        else:
            verdict = "mixed"
    else:
        verdict = "n/a"

    return {
        "bpm": round(tempo, 1),
        "setcpm": f"setcpm({round(tempo, 1)}/4)",
        "beats": int(len(beat_frames)),
        "onsets": int(counted),
        "grid16": grid,
        "grid_str": "".join("." if c == 0 else ("X" if c > max(grid or [1]) * 0.6 else "x") for c in grid),
        "feel": verdict,
        "straightErr": round(straight_err, 3),
        "tripletErr": round(triplet_err, 3),
    }


def make_test_clip(sr: int = 22050, bpm: float = 90.0) -> np.ndarray:
    """Synthesize a straight-16th 'X.XX' cumbia-style click for a self-test."""
    beat = 60.0 / bpm
    sixteenth = beat / 4
    total = beat * 4 * 4  # 4 bars
    y = np.zeros(int(total * sr))
    click = np.exp(-np.linspace(0, 6, int(0.02 * sr))) * np.sin(
        2 * np.pi * 2000 * np.linspace(0, 0.02, int(0.02 * sr))
    )
    # X.XX per beat -> hit on 16ths 0,2,3 (rest on the "e" = index 1)
    hits_per_beat = [0, 2, 3]
    n_beats = int(total / beat)
    for b in range(n_beats):
        for s in hits_per_beat:
            start = int((b * beat + s * sixteenth) * sr)
            end = min(start + len(click), len(y))
            y[start:end] += click[: end - start]
    return y.astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audio -> Strudel rhythm analysis (Phase 1).")
    ap.add_argument("audio", nargs="?", help="path to a WAV/FLAC/MP3 clip")
    ap.add_argument("--bars", type=int, default=4)
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    ap.add_argument("--bands", action="store_true", help="split into low/mid/high percussion registers")
    ap.add_argument("--key", action="store_true", help="estimate musical key (chroma / Krumhansl-Schmuckler)")
    ap.add_argument("--bassline", action="store_true", help="pitch-track the bass (note per beat)")
    ap.add_argument("--chords", action="store_true", help="chord progression via beat-sync chroma templates")
    ap.add_argument("--per-beat", action="store_true", help="with --chords: label every beat (default: per bar)")
    ap.add_argument("--selftest", action="store_true", help="synthesize & analyze a 90 BPM clip")
    args = ap.parse_args()

    if args.selftest:
        sr = 22050
        y = make_test_clip(sr=sr)
    elif args.audio:
        import librosa

        y, sr = librosa.load(args.audio, sr=None, mono=True)
    else:
        ap.print_help()
        return 1

    if args.key:
        k = estimate_key(y, sr)
        print(f"key = {k['key']}   (confidence {k['confidence']})")
        return 0

    if args.bassline:
        b = extract_bassline(y, sr)
        print(f"bpm={b['bpm']}  beats={b['beats']}")
        print("note per beat:")
        print("  " + " ".join(b["notes_per_beat"]))
        return 0

    if args.chords:
        c = chord_progression(y, sr, per_bar=not args.per_beat)
        print(f"bpm={c['bpm']}   chord per {c['unit']}:")
        print("  " + " | ".join(c["chords"]))
        return 0

    # --bands: share one tempo, report a grid per frequency register
    if args.bands:
        import librosa

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        tempo = float(np.atleast_1d(tempo)[0])
        print(f"bpm={round(tempo,1)}   ->   setcpm({round(tempo,1)}/4)   (shared across bands)\n")
        for label, (lo, hi) in BANDS.items():
            yb = bandpass(y, sr, lo, hi)
            r = analyze(yb, sr, bars=args.bars, fixed_tempo=tempo)
            acc = accent_grid(yb, sr, tempo)
            print(f"{label:22} onsets |{r['grid_str']}|")
            print(f"{'':22} accent |{render_levels(acc)}|  feel={r['feel']}")
        print("\nonsets: X=hit x=weak .=rest   accent: @=loud ... .=soft ' '=silent")
        print("the guira 'chu-[gap]-chuchu' shows as an ACCENT dip on the 2nd 16th, not a rest.")
        return 0

    result = analyze(y, sr, bars=args.bars)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"bpm={result['bpm']}   ->   {result['setcpm']}")
        print(f"beats={result['beats']}  onsets={result['onsets']}")
        print(f"bar grid (16ths):  |{result['grid_str']}|")
        print(f"feel={result['feel']}  (straightErr={result['straightErr']} tripletErr={result['tripletErr']})")
        print("\nX=strong onset, x=weak, .=rest. feel compares onsets to straight-16th vs triplet grid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
