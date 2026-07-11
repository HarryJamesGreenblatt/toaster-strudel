#!/usr/bin/env python
"""resolve_instruments.py — map inferred instruments onto the Strudel palette.

The instrument-inference METHOD (web research -> genre convention -> audio arbiter)
is agent-driven and produces raw real-world instrument NAMES with confidence. This
tool is the deterministic last mile: it maps each name onto an actually-available
Strudel sound (mir/sound_palette.json), flags PROXIES (no exact match; nearest
substitute) and GAPS (nothing suitable), so the reproduction whitelist is bounded
by what Strudel can really make.

Input (any of):
    * a Song IR `context` JSON on stdin/--in, with `instruments` = list of names
      or list of {name, confidence?, source?}
    * `--instruments "accordion,guira,conga,bass"`

Output: context with `instruments` resolved to
    {name, strudel_sound, role, proxy, confidence, source, note?, gap?}

Usage:
    python resolve_instruments.py --instruments "orchestra hit,choir,synth strings,bass"
    identify.py --json x | linernotes.py --json | resolve_instruments.py --instruments "..."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PALETTE_PATH = Path(__file__).resolve().parent / "sound_palette.json"


def load_palette() -> dict:
    return json.loads(PALETTE_PATH.read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return " ".join(s.lower().strip().replace("-", " ").split())


def resolve_one(name: str, aliases: dict) -> dict:
    n = _norm(name)
    # 1. exact alias
    if n in aliases:
        return {**aliases[n], "matched": n}
    # 2. singular/plural nudge
    if n.endswith("s") and n[:-1] in aliases:
        return {**aliases[n[:-1]], "matched": n[:-1]}
    # 3. substring both directions; prefer the longest alias key that fits
    cands = [k for k in aliases if k in n or n in k]
    if cands:
        best = max(cands, key=len)
        return {**aliases[best], "matched": best}
    # 4. no match -> gap
    return {"sound": None, "role": None, "proxy": None, "gap": True, "matched": None}


def resolve(raw_list: list, palette: dict) -> list:
    aliases = palette["aliases"]
    out = []
    for item in raw_list:
        if isinstance(item, dict):
            name = item.get("name", "")
            confidence = item.get("confidence", "medium")
            source = item.get("source", [])
        else:
            name, confidence, source = str(item), "medium", []
        r = resolve_one(name, aliases)
        entry = {
            "name": name,
            "strudel_sound": r.get("sound"),
            "role": r.get("role"),
            "proxy": r.get("proxy"),
            "confidence": confidence,
            "source": source,
        }
        if r.get("note"):
            entry["note"] = r["note"]
        if r.get("gap"):
            entry["gap"] = True
        out.append(entry)
    return out


def read_input(args) -> tuple[dict, list]:
    ctx: dict = {}
    if args.in_file:
        ctx = json.loads(Path(args.in_file).read_text(encoding="utf-8"))
    elif not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            ctx = json.loads(raw)
    raw_list = list(ctx.get("instruments", []))
    if args.instruments:
        raw_list = [s.strip() for s in args.instruments.split(",") if s.strip()]
    return ctx, raw_list


def main() -> int:
    ap = argparse.ArgumentParser(description="Map inferred instruments onto the Strudel palette.")
    ap.add_argument("--in", dest="in_file", help="context JSON file")
    ap.add_argument("--instruments", help='comma-separated instrument names, e.g. "accordion,guira,conga"')
    ap.add_argument("--json", action="store_true", help="emit only the JSON block")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    ctx, raw_list = read_input(args)
    if not raw_list:
        print("error: no instruments given (pass --instruments or a context with 'instruments')",
              file=sys.stderr)
        return 2

    palette = load_palette()
    resolved = resolve(raw_list, palette)
    ctx["instruments"] = resolved

    print(json.dumps(ctx, indent=2, ensure_ascii=False))
    if not args.json:
        print("", file=sys.stderr)
        for e in resolved:
            if e.get("gap"):
                print(f"  {e['name']:<18} -> (NO SOUND - gap)", file=sys.stderr)
            else:
                tag = " ~proxy" if e["proxy"] else ""
                print(f"  {e['name']:<18} -> {e['strudel_sound']}{tag}", file=sys.stderr)
        gaps = [e["name"] for e in resolved if e.get("gap")]
        if gaps:
            print(f"\n  gaps (no Strudel sound): {', '.join(gaps)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
