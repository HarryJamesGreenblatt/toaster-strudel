#!/usr/bin/env python
"""identify.py — Shazam-grade track identification (LEFT side, pipeline stage 0).

Turns an unlabeled audio file into an identity so you don't have to embed song
info in filenames. Fallback chain, most reliable first:

    1. shazamio   -> Shazam's recognition backend. Broad commercial coverage;
                     recognizes real tracks AND short excerpts. Returns identity
                     PLUS liner-notes metadata (album/label/year/genre/ISRC).
    2. AcoustID   -> free, crowd-sourced. Thin coverage, but can add a
                     MusicBrainz recording ID when it does match.
    3. filename   -> graceful last resort.

Emits the ``context`` seed of the Song IR as JSON on stdout, plus a human summary
on stderr.

Usage:
    python identify.py <audiofile> [--json] [--no-shazam] [--min-score 0.5]

Requires:
    * shazamio (pip)                — primary recognizer
    * ACOUSTID_CLIENT_KEY + fpcalc  — only for the AcoustID fallback
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests

from secret_store import get_secret

ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
USER_AGENT = "toaster-strudel/0.1 (+https://github.com/HarryJamesGreenblatt/toaster-strudel)"


# --------------------------------------------------------------------------- #
# Primary recognizer: shazamio
# --------------------------------------------------------------------------- #
def recognize_shazam(audio: Path) -> dict | None:
    """Recognize via Shazam's backend. Returns the ``track`` dict, or None."""
    try:
        from shazamio import Shazam
    except ImportError:
        return None

    async def _run() -> dict:
        return await Shazam().recognize(str(audio))

    try:
        out = asyncio.run(_run())
    except Exception as exc:  # network / decode / no-match
        print(f"(shazam unavailable: {exc})", file=sys.stderr)
        return None
    track = out.get("track") if isinstance(out, dict) else None
    return track or None


def to_context_shazam(track: dict) -> dict:
    """Shape a Shazam track into the Song IR `context` block (incl. liner notes)."""
    rows = {}
    for sec in track.get("sections", []):
        if sec.get("type") == "SONG":
            for row in sec.get("metadata", []) or []:
                rows[row.get("title")] = row.get("text")
    isrc = track.get("isrc") or (track.get("hub") or {}).get("isrc")
    return {
        "identified": True,
        "recognizer": "shazam",
        "title": track.get("title"),
        "artist": track.get("subtitle"),
        "album": rows.get("Album"),
        "label": rows.get("Label"),
        "year": rows.get("Released"),
        "genre": (track.get("genres") or {}).get("primary"),
        "isrc": isrc,
        "shazam_key": track.get("key"),
        "url": track.get("url"),
        "source": ["shazam"],
    }


# --------------------------------------------------------------------------- #
# Fallback recognizer: AcoustID (Chromaprint fingerprint)
# --------------------------------------------------------------------------- #
def find_fpcalc() -> str:
    """Locate fpcalc: PATH first, then the winget package dir (PATH may be stale)."""
    exe = shutil.which("fpcalc")
    if exe:
        return exe
    base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    hits = glob.glob(os.path.join(base, "AcoustID.Chromaprint*", "**", "fpcalc.exe"), recursive=True)
    if hits:
        return hits[0]
    raise RuntimeError("fpcalc not found. Install with: winget install AcoustID.Chromaprint")


def fingerprint(audio: Path) -> tuple[int, str]:
    """Return (duration_seconds, fingerprint) via fpcalc -json."""
    proc = subprocess.run([find_fpcalc(), "-json", str(audio)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"fpcalc failed on {audio.name}:\n{proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    return int(round(data["duration"])), data["fingerprint"]


def acoustid_lookup(audio: Path, min_score: float) -> dict | None:
    """AcoustID fallback. Returns a `context` block, or None on no usable match."""
    key = get_secret("ACOUSTID_CLIENT_KEY", required=False)
    if not key:
        return None
    try:
        duration, fp = fingerprint(audio)
    except RuntimeError as exc:
        print(f"(acoustid unavailable: {exc})", file=sys.stderr)
        return None
    resp = requests.post(
        ACOUSTID_URL,
        data={"client": key, "duration": duration, "fingerprint": fp,
              "meta": "recordings+releasegroups+usermeta"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    results = [r for r in payload.get("results", []) if r.get("score", 0) >= min_score]
    if not results:
        return None
    result = max(results, key=lambda r: r.get("score", 0))
    recs = result.get("recordings")
    if not recs:
        return {
            "identified": "fingerprint_only",
            "recognizer": "acoustid",
            "acoustid": result.get("id"),
            "score": round(result.get("score", 0), 3),
            "note": "fingerprint matched AcoustID but has no linked metadata",
            "source": ["acoustid"],
        }
    rec = recs[0]
    rgs = rec.get("releasegroups", [])
    return {
        "identified": True,
        "recognizer": "acoustid",
        "title": rec.get("title"),
        "artist": ", ".join(a["name"] for a in rec.get("artists", [])) or None,
        "release": rgs[0].get("title") if rgs else None,
        "recording_mbid": rec.get("id"),
        "release_group_mbid": rgs[0].get("id") if rgs else None,
        "acoustid": result.get("id"),
        "score": round(result.get("score", 0), 3),
        "source": ["acoustid", "musicbrainz"],
    }


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Identify a track (Shazam, then AcoustID).")
    ap.add_argument("audio", type=Path)
    ap.add_argument("--json", action="store_true", help="emit only the JSON context block")
    ap.add_argument("--no-shazam", action="store_true", help="skip Shazam, use AcoustID only")
    ap.add_argument("--min-score", type=float, default=0.5, help="min AcoustID score (0..1)")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    if not args.audio.exists():
        print(f"error: no such file: {args.audio}", file=sys.stderr)
        return 2

    ctx = None
    if not args.no_shazam:
        track = recognize_shazam(args.audio)
        if track:
            ctx = to_context_shazam(track)
    if ctx is None:
        ctx = acoustid_lookup(args.audio, args.min_score)
    if ctx is None:
        ctx = {"identified": False, "fallback_label": args.audio.stem, "source": ["filename"]}

    print(json.dumps(ctx, indent=2, ensure_ascii=False))
    if not args.json:
        if ctx.get("identified") is True:
            head = " ".join(b for b in [ctx.get("artist"), "-", ctx.get("title")] if b)
            extra = " | ".join(
                x for x in [ctx.get("album"), ctx.get("label"), ctx.get("year"), ctx.get("genre")] if x
            )
            print(f"\n{head}{('  [' + extra + ']') if extra else ''}"
                  f"   (via {ctx.get('recognizer')})", file=sys.stderr)
        elif ctx.get("identified") == "fingerprint_only":
            print(f"\nFingerprint recognized (score {ctx.get('score')}) but unlinked. "
                  f"Use name search.", file=sys.stderr)
        else:
            print(f"\nNot recognized. Falling back to filename: {ctx.get('fallback_label')!r}",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
