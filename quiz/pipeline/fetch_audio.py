"""Harvest xeno-canto recordings for the audio quiz.

    set XC_API_KEY=...
    ~/anaconda3/python.exe quiz/pipeline/fetch_audio.py
    ~/anaconda3/python.exe quiz/pipeline/fetch_audio.py --limit 20
    ~/anaconda3/python.exe quiz/pipeline/fetch_audio.py --pack-only

Same split as the photographs: the metadata is harvested once and committed,
the audio itself is streamed from xeno-canto at play time. Their API needs a
key and this repo is public, so the key can only ever live at harvest time -
it is read from XC_API_KEY and never written anywhere. The audio files
themselves need no key, which is what makes the split work.

Region tiers, nearest first. A species stops as soon as it has enough, so a
Chiapas bird never costs more than one request and only the rarities walk the
whole ladder. The quiz does not say which tier a recording came from; it is a
sourcing decision, not something the listener needs.

    box     the Chiapas bounding box - xeno-canto has no region codes, so
            state-level filtering has to be geographic
    Mexico
    Guatemala
    world

Writes src/lib/data/quiz/audio.json. Raw responses are cached in
quiz/data/raw/audio_xc.json so re-packing costs nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

API = "https://xeno-canto.org/api/3/recordings"
UA = "BirdQuiz/1.0 (personal study tool; github.com/counttakeshi/bird-quiz)"

# Chiapas, as south,west,north,east. xeno-canto has no region codes, so a state
# has to be a box. Drawn wide enough to keep the coast and the Guatemalan
# border, which is where a good deal of the interesting recording happens.
CHIAPAS_BOX = "box:14.5,-94.2,18.0,-90.3"

TIERS = [
    ("chiapas", CHIAPAS_BOX),
    ("mexico", 'cnt:"Mexico"'),
    ("guatemala", 'cnt:"Guatemala"'),
    ("world", ""),
]
TIER_INDEX = {name: i for i, (name, _) in enumerate(TIERS)}

# Enough for a quiz to not repeat itself within a session, without making the
# bundle carry recordings nobody will reach.
WANT = 8

# xeno-canto's own A-E. Anything below C is usually unusable for a quiz:
# distant, windy, or the bird is one voice in a dawn chorus.
QUALITY = ["A", "B", "C", "D", "E"]
MAX_QUALITY_RANK = 2

SOUND_TYPES = ["song", "call", "other"]

REQUEST_DELAY = 0.6

RAW = common.DATA / "raw" / "audio_xc.json"
OUT = common.ROOT / "src" / "lib" / "data" / "quiz" / "audio.json"
INDEX = common.ROOT / "src" / "lib" / "data" / "quiz" / "index.json"


class Unauthorized(Exception):
    """The key is missing, wrong, or has been revoked."""


def key() -> str:
    value = (os.environ.get("XC_API_KEY") or "").strip()
    if not value:
        raise SystemExit(
            "No XC_API_KEY in the environment.\n"
            "Get one from your xeno-canto account page and set it for this "
            "shell only - it must not be committed:\n"
            '    PowerShell:  $env:XC_API_KEY = "..."\n'
            '    bash:        export XC_API_KEY="..."'
        )
    return value


def search(query: str, api_key: str) -> list[dict]:
    """One page of recordings. 100 is plenty: we keep at most eight."""
    url = API + "?" + urllib.parse.urlencode(
        {"query": query, "key": api_key, "per_page": 100}
    )
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            raise Unauthorized(f"HTTP {err.code} for {query}") from err
        # 400 is a query the API would not parse - a species whose name has
        # something in it the tag syntax dislikes. Report it and move on
        # rather than losing the whole run to one bird.
        if err.code == 400:
            print(f"    ! rejected: {query}")
            return []
        raise
    finally:
        time.sleep(REQUEST_DELAY)
    return payload.get("recordings") or []


def taxon_query(scientific: str) -> str:
    """`gen:` and `sp:` rather than a bare name, which v3 will not parse."""
    parts = scientific.split()
    if len(parts) >= 2:
        return f"gen:{parts[0]} sp:{parts[1]}"
    return f"gen:{parts[0]}" if parts else ""


def seconds(length: str) -> int:
    """xeno-canto writes 'm:ss' or 'h:mm:ss'."""
    try:
        total = 0
        for part in str(length).strip().split(":"):
            total = total * 60 + int(part)
        return total
    except (TypeError, ValueError):
        return 9999


def sound_type(raw: str) -> str:
    """Collapse the free-text type down to song, call, or other.

    The field is open, so it holds things like 'song, alarm call' and
    'flight call'. Song wins a tie: it is the more diagnostic of the two and
    the one a birder is usually learning.
    """
    text = (raw or "").lower()
    if "song" in text:
        return "song"
    if "call" in text:
        return "call"
    return "other"


def rank(recording: dict) -> tuple:
    """Best quality first, then shortest.

    Short matters more here than it does for a photograph: a two-minute
    recording of a dawn chorus is a worse question than twenty seconds of one
    bird, whatever its rating.
    """
    quality = QUALITY.index(recording.get("q", "").upper()) if recording.get(
        "q", ""
    ).upper() in QUALITY else 9
    return (quality, seconds(recording.get("length", "")))


def usable(recording: dict) -> bool:
    quality = (recording.get("q") or "").upper()
    if quality not in QUALITY or QUALITY.index(quality) > MAX_QUALITY_RANK:
        return False
    length = seconds(recording.get("length", ""))
    # Under two seconds is usually a clipped fragment; over three minutes is a
    # soundscape that happens to have the bird in it.
    return 2 <= length <= 180


def harvest(codes: dict[str, str], cache: dict, api_key: str, limit: int | None) -> dict:
    """Walk the tiers for every species that does not already have enough."""
    done = skipped = 0
    for code, scientific in codes.items():
        if limit is not None and done >= limit:
            break
        held = cache.get(code)
        if held is not None and len(held.get("r", [])) >= WANT:
            skipped += 1
            continue

        taxon = taxon_query(scientific)
        if not taxon:
            continue

        kept: list[dict] = []
        seen: set[int] = set()
        for tier_name, clause in TIERS:
            if len(kept) >= WANT:
                break
            query = f"{taxon} {clause}".strip()
            try:
                records = search(query, api_key)
            except Unauthorized:
                raise
            for record in sorted((r for r in records if usable(r)), key=rank):
                try:
                    identifier = int(record.get("id"))
                except (TypeError, ValueError):
                    continue
                if identifier in seen:
                    continue
                seen.add(identifier)
                record["_tier"] = tier_name
                kept.append(record)
                if len(kept) >= WANT:
                    break

        cache[code] = {"r": kept}
        done += 1
        tiers = sorted({r["_tier"] for r in kept})
        state = f"{len(kept):2} recordings [{', '.join(tiers) or 'none'}]"
        print(f"  {code:<10} {scientific:<30} {state}")

        if done % 25 == 0:
            RAW.parent.mkdir(parents=True, exist_ok=True)
            RAW.write_text(json.dumps(cache), encoding="utf-8")

    print(f"\n{done} species fetched, {skipped} already had enough")
    return cache


def pack(cache: dict) -> dict:
    """Compact the cache the same way photos.json is packed.

    Recordists and licences are shared across every species and repeat
    heavily, so they are stored once and referenced by index. The rest of a
    recording fits in one integer.
    """
    recordists: list[str] = []
    licences: list[str] = []
    recordist_index: dict[str, int] = {}
    licence_index: dict[str, int] = {}

    def intern(value: str, table: list[str], index: dict[str, int]) -> int:
        value = (value or "").strip()
        if value not in index:
            index[value] = len(table)
            table.append(value)
        return index[value]

    species: dict[str, list] = {}
    for code, held in sorted(cache.items()):
        rows = []
        for record in held.get("r", []):
            try:
                identifier = int(record.get("id"))
            except (TypeError, ValueError):
                continue
            quality = (record.get("q") or "").upper()
            # bits 0-2 quality, bits 3-4 sound type, bits 5-6 region tier
            flags = QUALITY.index(quality) if quality in QUALITY else 7
            flags |= SOUND_TYPES.index(sound_type(record.get("type"))) << 3
            flags |= TIER_INDEX.get(record.get("_tier", "world"), 3) << 5
            rows.append(
                [
                    identifier,
                    flags,
                    intern(record.get("rec"), recordists, recordist_index),
                    intern(record.get("lic"), licences, licence_index),
                    seconds(record.get("length", "")),
                ]
            )
        if rows:
            species[code] = rows

    return {"c": recordists, "l": licences, "s": species}


def report(packed: dict, codes: dict[str, str]) -> None:
    species = packed["s"]
    total = sum(len(rows) for rows in species.values())
    print()
    print(f"{len(species)} of {len(codes)} species have a recording")
    print(f"{total:,} recordings, {len(packed['c']):,} recordists, {len(packed['l'])} licences")

    tiers = {name: 0 for name, _ in TIERS}
    types = {name: 0 for name in SOUND_TYPES}
    for rows in species.values():
        for row in rows:
            tiers[TIERS[(row[1] >> 5) & 3][0]] += 1
            types[SOUND_TYPES[(row[1] >> 3) & 3]] += 1
    print()
    print("  by region tier")
    for name, count in tiers.items():
        print(f"    {name:<12} {count:>7,}")
    print("  by sound type")
    for name, count in types.items():
        print(f"    {name:<12} {count:>7,}")

    missing = [c for c in codes if c not in species]
    print()
    print(f"{len(missing)} species have nothing usable")
    for code in missing[:10]:
        print(f"    {code:<10} {codes[code]}")
    if len(missing) > 10:
        print(f"    ... and {len(missing) - 10} more")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="fetch at most this many species")
    parser.add_argument(
        "--pack-only",
        action="store_true",
        help="rebuild audio.json from the cache without calling the API",
    )
    args = parser.parse_args()

    entries = json.loads(INDEX.read_text(encoding="utf-8"))
    codes = {e["c"]: e.get("s", "") for e in entries if e.get("s")}
    print(f"{len(codes)} species in the shared index")

    cache = json.loads(RAW.read_text(encoding="utf-8")) if RAW.exists() else {}

    if not args.pack_only:
        try:
            cache = harvest(codes, cache, key(), args.limit)
        except Unauthorized as err:
            print(f"\nxeno-canto rejected the key: {err}")
            print("Check XC_API_KEY. Nothing was lost - the cache is written as it goes.")
            return 1
        finally:
            RAW.parent.mkdir(parents=True, exist_ok=True)
            RAW.write_text(json.dumps(cache), encoding="utf-8")

    packed = pack(cache)
    OUT.write_text(json.dumps(packed, separators=(",", ":")), encoding="utf-8")
    report(packed, codes)
    print()
    print(f"wrote {OUT.relative_to(common.ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
