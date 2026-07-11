#!/usr/bin/env python
"""linernotes.py — deep liner-notes enrichment (LEFT side, pipeline stage 0.5).

Takes an identity (ideally from identify.py) and gathers the "liner notes" that
GROUND a reproduction: personnel, instruments, writers/producers, styles, and
production notes. Structured sources:

    * MusicBrainz  (no key) — ISRC/name -> recording relationships:
                    arrangers, producers, performers, instrument credits, releases.
    * Discogs      (token)  — release credits (extraartists), genres/styles, notes.

Instrument/gear detail (e.g. a Fairlight CMI) is often NOT in the per-single API
data; it lives in album notes / encyclopaedic sources. This tool collects the
structured credits and flags when instruments are sparse so the agent can add a
targeted web pass.

Input (any of):
    * a Song IR `context` JSON on stdin (e.g. `identify.py --json x | linernotes.py`)
    * `--in context.json`
    * explicit `--isrc` / `--artist` / `--title`

Output: the enriched `context` block as JSON on stdout + a human summary on stderr.

Usage:
    python identify.py --json song.wav | python linernotes.py
    python linernotes.py --isrc GBAHW0800138 --artist "Art of Noise" --title "Moments In Love"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

from secret_store import get_secret

MB_BASE = "https://musicbrainz.org/ws/2"
DISCOGS_BASE = "https://api.discogs.com"
UA = "toaster-strudel/0.1 (+https://github.com/HarryJamesGreenblatt/toaster-strudel)"

# Role/attribute keywords that denote an instrument or piece of gear.
INSTRUMENT_HINTS = (
    "synth", "fairlight", "cmi", "sampler", "keyboard", "piano", "organ", "rhodes",
    "guitar", "bass", "drum", "percussion", "vibraphone", "marimba", "strings",
    "violin", "cello", "brass", "sax", "trumpet", "flute", "accordion", "programming",
    "emulator", "prophet", "moog", "oberheim", "linn", "808", "909", "mellotron",
)


def _get(url: str, params: dict, rate: float = 0.0) -> dict:
    resp = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    if rate:
        time.sleep(rate)  # respect MusicBrainz ~1 req/sec
    return resp.json()


# --------------------------------------------------------------------------- #
# MusicBrainz
# --------------------------------------------------------------------------- #
def mb_find_recording(isrc: str | None, artist: str | None, title: str | None) -> str | None:
    if isrc:
        data = _get(f"{MB_BASE}/recording", {"query": f"isrc:{isrc}", "fmt": "json"}, rate=1.1)
        recs = data.get("recordings", [])
        if recs:
            return recs[0]["id"]
    if artist and title:
        q = f'artist:"{artist}" AND recording:"{title}"'
        data = _get(f"{MB_BASE}/recording", {"query": q, "fmt": "json"}, rate=1.1)
        recs = data.get("recordings", [])
        if recs:
            return recs[0]["id"]
    return None


def mb_details(mbid: str) -> dict:
    rec = _get(
        f"{MB_BASE}/recording/{mbid}",
        {"inc": "artist-rels+work-rels+releases+artist-credits", "fmt": "json"},
        rate=1.1,
    )
    personnel, instruments = [], set()
    for rel in rec.get("relations", []):
        artist = (rel.get("artist") or {}).get("name")
        if not artist:
            continue
        role = rel.get("type")
        attrs = rel.get("attributes", []) or []
        entry = {"name": artist, "role": role, "source": "musicbrainz"}
        if attrs:
            entry["detail"] = attrs
        personnel.append(entry)
        if role == "instrument":
            instruments.update(attrs)
        elif any(h in (role or "").lower() for h in INSTRUMENT_HINTS):
            instruments.add(role)
    releases = [
        {"title": r.get("title"), "date": r.get("date")}
        for r in rec.get("releases", [])[:5]
    ]
    return {"mbid": mbid, "personnel": personnel,
            "instruments": sorted(instruments), "releases": releases}


# --------------------------------------------------------------------------- #
# Discogs
# --------------------------------------------------------------------------- #
def discogs_release(artist: str | None, title: str | None) -> dict | None:
    token = get_secret("DISCOGS_TOKEN", required=False)
    if not token or not (artist and title):
        return None
    hits = _get(
        f"{DISCOGS_BASE}/database/search",
        {"q": f"{artist} {title}", "type": "release", "token": token, "per_page": 5},
    ).get("results", [])
    if not hits:
        return None
    rid = hits[0]["id"]
    rel = _get(f"{DISCOGS_BASE}/releases/{rid}", {"token": token})
    credits, instruments = [], set()
    for c in rel.get("extraartists", []) or []:
        name, role = c.get("name"), c.get("role")
        credits.append({"name": name, "role": role, "source": "discogs"})
        if role and any(h in role.lower() for h in INSTRUMENT_HINTS):
            instruments.add(role)
    return {
        "release_id": rid,
        "release_title": rel.get("title"),
        "genres": rel.get("genres"),
        "styles": rel.get("styles"),
        "credits": credits,
        "instruments": sorted(instruments),
        "notes": (rel.get("notes") or "").strip()[:600] or None,
    }


# --------------------------------------------------------------------------- #
def read_input(args) -> dict:
    ctx: dict = {}
    if args.in_file:
        ctx = json.loads(Path(args.in_file).read_text(encoding="utf-8"))
    elif not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            ctx = json.loads(raw)
    # explicit flags override
    if args.isrc:
        ctx["isrc"] = args.isrc
    if args.artist:
        ctx["artist"] = args.artist
    if args.title:
        ctx["title"] = args.title
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich a track identity with liner notes.")
    ap.add_argument("--in", dest="in_file", help="context JSON file (from identify.py)")
    ap.add_argument("--isrc")
    ap.add_argument("--artist")
    ap.add_argument("--title")
    ap.add_argument("--json", action="store_true", help="emit only the JSON block")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    ctx = read_input(args)
    isrc, artist, title = ctx.get("isrc"), ctx.get("artist"), ctx.get("title")
    if not (isrc or (artist and title)):
        print("error: need an ISRC or artist+title (pipe identify.py --json, or pass flags)",
              file=sys.stderr)
        return 2

    sources = set(ctx.get("source", []))
    liner: dict = {}

    mbid = mb_find_recording(isrc, artist, title)
    if mbid:
        mb = mb_details(mbid)
        liner["musicbrainz"] = mb
        sources.add("musicbrainz")

    dc = discogs_release(artist, title)
    if dc:
        liner["discogs"] = dc
        sources.add("discogs")

    # Merge a flat, deduped view for downstream priming.
    personnel = (liner.get("musicbrainz", {}).get("personnel", [])
                 + liner.get("discogs", {}).get("credits", []))
    instruments = sorted(set(liner.get("musicbrainz", {}).get("instruments", [])
                             + liner.get("discogs", {}).get("instruments", [])))
    styles = liner.get("discogs", {}).get("styles") or ([ctx.get("genre")] if ctx.get("genre") else [])

    ctx["liner_notes"] = liner
    ctx["personnel"] = personnel
    ctx["instruments"] = instruments
    ctx["styles"] = styles
    ctx["source"] = sorted(sources)

    print(json.dumps(ctx, indent=2, ensure_ascii=False))
    if not args.json:
        who = ", ".join(f"{p['name']} ({p['role']})" for p in personnel[:8]) or "-"
        print(f"\n{artist} - {title}", file=sys.stderr)
        print(f"  styles: {', '.join(styles) if styles else '—'}", file=sys.stderr)
        print(f"  personnel: {who}", file=sys.stderr)
        print(f"  instruments: {', '.join(instruments) if instruments else '(none in API - web pass advised)'}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
