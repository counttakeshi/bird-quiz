

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import plumage  # noqa: E402

SEARCH = "https://search.macaulaylibrary.org/api/v2/search"
UA = "BirdQuiz/1.0 (personal study tool; github.com/counttakeshi/bird-quiz)"

CACHE = common.RAW / (os.environ.get("QUIZ_PHOTO_CACHE") or "photos_ml.json")
OUT = common.ROOT / "src" / "lib" / "data" / "quiz" / "photos.json"

PER_SPECIES = 50


MIN_RATING = 2.5


MEXICAN_SHARE = 30
SINGLE_REQUEST = True

MAX_PER_CHECKLIST = 1

POOL = 500


PAUSE = 4.0
COOLDOWN = 120        # 2 minutes, in case it was only a hiccup
GIVE_UP_AFTER = 2     # then exit and let the watcher wait

# The iNaturalist harvest this replaced. Macaulay is the better source but is
# rate-limited to a crawl, so those photographs stay on as a fallback for the
# species Macaulay has not reached yet. The quiz labels which is which and
# always prefers Macaulay where it has it.
INAT_CACHE = common.RAW / "photos_inat.json"
INAT_HOSTS = [
    "https://inaturalist-open-data.s3.amazonaws.com",
    "https://static.inaturalist.org",
]
INAT_EXTS = ["jpg", "jpeg", "png", "gif", "JPG"]

# Every asset is one id against one CDN, so the wire format is far simpler than
# it had to be for iNaturalist. Keep in step with src/lib/quiz/photos.ts.
CDN = "https://cdn.download.ams.birds.cornell.edu/api/v2/asset"

# 900 is roughly the widest the quiz plate ever renders; 1200 covers a retina
# phone without pulling multi-megabyte originals for every question.
IMAGE_SIZE = 1200


# ── cache entries ───────────────────────────────────────────────────────────
# An entry is {"w": how many we asked for, "p": [photo, ...]}. The `w` is what
# stops a top-up run refetching every thin species forever: a bird with 9
# photographs above the rating floor will never reach 50, and without recording
# that we asked for 50 we would try again on every single run.


def entry_photos(value) -> list[dict]:
    return value["p"] if isinstance(value, dict) else (value or [])


def entry_want(value) -> int:
    return value.get("w", 0) if isinstance(value, dict) else 0


class Challenged(Exception):
    """Macaulay served its proof-of-work page instead of an answer.

    The search API has no published rate limit and answers happily for a while,
    then starts returning an HTML "Making sure you're not a bot!" page with a
    200 status. It is rate-triggered, and once tripped it stays tripped for a
    good while - not a per-request hiccup to retry through.

    Let's try and solve this perhaps by changing IP.
    """


def search(code: str, region: str | None) -> list[dict]:
    """One page of the best-ranked photographs for a species."""
    params = {
        "taxonCode": code,
        "mediaType": "photo",
        "count": POOL,
        "sort": "rating_rank_desc",
    }
    if region:
        params["regionCode"] = region
    r = requests.get(SEARCH, params=params, headers={"User-Agent": UA}, timeout=90)
    r.raise_for_status()
    # The challenge comes back as HTML with a 200, so the status tells you
    # nothing. The content type does.
    if "json" not in (r.headers.get("content-type") or ""):
        raise Challenged(f"{code}: proof-of-work page instead of results")
    data = r.json()
    return data if isinstance(data, list) else []


def eligible(records: list[dict], code: str) -> tuple[list[dict], int]:
    """Keep the records that are the right bird, well enough photographed.

    Returns the survivors and how many were rejected for being the wrong taxon -
    which should always be zero, and is checked anyway.
    """
    kept, wrong = [], 0
    for rec in records:
        taxonomy = rec.get("taxonomy") or {}
        # `species` is the plain record; `issf` is an identifiable subspecies
        # group - Crane Hawk (Blackish), (Banded), (Gray) - which eBird reports
        # *as* the species. Those belong here: the quiz asks which species this
        # is, and a Crane Hawk in all three of its plumages is better teaching
        # than 454 of the nominate. Anything else - hybrids, "sp.", slashes -
        # is not a clean answer to that question.
        same = code in (taxonomy.get("speciesCode"), taxonomy.get("reportAs"))
        if not same or taxonomy.get("category") not in ("species", "issf"):
            wrong += 1
            continue
        if (rec.get("rating") or 0) < MIN_RATING:
            continue
        if rec.get("restricted"):
            continue  # location-sensitive species; Macaulay asks that these stay put
        if not rec.get("assetId"):
            continue
        kept.append(rec)
    return kept, wrong


def thin_by_checklist(records: list[dict], cap: int) -> list[dict]:
    """At most `cap` photographs from any one checklist."""
    seen: dict[str, int] = {}
    out = []
    for rec in records:
        key = rec.get("ebirdChecklistId") or f"asset{rec['assetId']}"
        if seen.get(key, 0) >= cap:
            continue
        seen[key] = seen.get(key, 0) + 1
        out.append(rec)
    return out


def to_photo(rec: dict, mexican: bool) -> dict:
    return {
        "a": rec["assetId"],
        "by": rec.get("userDisplayName") or "",
        "l": rec.get("licenseId") or "",
        "r": round(float(rec.get("rating") or 0), 2),
        "mx": mexican,
    }


def fetch_species(code: str, want: int) -> tuple[list[dict], int, bool]:
    """Photographs for one species: Mexican checklists first, then anywhere.

    Both pools are sampled rather than taken from the top. Taking the top 50
    gives you fifty portraits of a perched adult in golden hour, which is the
    one bird you never have trouble identifying.
    """
    wrong_total = 0
    chosen: list[dict] = []
    used: set[int] = set()
    failed = False

    if SINGLE_REQUEST:
        try:
            raw = search(code, None)
        except Challenged:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"    ! {code}: {type(exc).__name__} {exc}")
            time.sleep(PAUSE)
            return [], 0, True

        good, wrong_total = eligible(raw, code)
        good = thin_by_checklist(good, MAX_PER_CHECKLIST)

        # Mexican records first, then the rest, each sampled rather than taken
        # in rank order - the top of the list is fifty portraits of a perched
        # adult in golden hour, which is the bird nobody struggles with.
        mexican = [r for r in good if (r.get("location") or {}).get("countryCode") == "MX"]
        elsewhere = [r for r in good if r not in mexican]
        picked = random.sample(mexican, min(MEXICAN_SHARE, len(mexican)))
        room = want - len(picked)
        picked += random.sample(elsewhere, min(room, len(elsewhere)))
        # Short on Mexican records? Top up from anywhere rather than run thin.
        if len(picked) < want:
            spare = [r for r in mexican if r not in picked]
            picked += random.sample(spare, min(want - len(picked), len(spare)))

        chosen = [
            to_photo(r, mexican=(r.get("location") or {}).get("countryCode") == "MX")
            for r in picked
        ]
        chosen.sort(key=lambda pp: -pp["r"])
        time.sleep(PAUSE)
        return chosen, wrong_total, False

    for region, quota in (("MX", min(MEXICAN_SHARE, want)), (None, want)):
        if len(chosen) >= want:
            break
        try:
            raw = search(code, region)
        except Challenged:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"    ! {code} ({region or 'world'}): {type(exc).__name__} {exc}")
            failed = True
            time.sleep(PAUSE)
            continue

        good, wrong = eligible(raw, code)
        wrong_total += wrong
        good = [r for r in good if r["assetId"] not in used]
        good = thin_by_checklist(good, MAX_PER_CHECKLIST)

        room = min(quota, want - len(chosen)) if region else want - len(chosen)
        take = random.sample(good, min(room, len(good)))
        for rec in take:
            used.add(rec["assetId"])
            chosen.append(to_photo(rec, mexican=region == "MX"))
        time.sleep(PAUSE)

    # Highest rated first, so a species with only a handful leads with its best.
    chosen.sort(key=lambda p: -p["r"])
    return chosen, wrong_total, failed


# iNaturalist bakes the licence into its attribution string, so this is the
# only signal available without re-querying their API.
ALL_RIGHTS_RESERVED = "all rights reserved"


def pack_inat() -> dict:
    """The old iNaturalist harvest, packed as a fallback block.

    Its records are shaped differently from Macaulay's - a photo id, a host, a
    file extension and an observation - so it keeps its own packing and its own
    credit table rather than being forced into one shared format.
    """
    photos: dict = {}
    for path in sorted(common.RAW.glob("photos_inat*.json")):
        try:
            for code, value in json.loads(path.read_text(encoding="utf-8")).items():
                if entry_photos(value):
                    photos[code] = value
        except (json.JSONDecodeError, OSError):
            continue

    credits: list[str] = []
    seen: dict[str, int] = {}
    species: dict[str, list] = {}

    restricted = 0

    for code, value in sorted(photos.items()):
        rows = []
        for photo in entry_photos(value):
            url = photo.get("u") or ""
            credit = photo.get("a") or ""
            # iNaturalist writes the licence into the attribution string, and a
            # good share of it is "all rights reserved" - the photographer
            # granted nothing. Macaulay's material is at least covered by their
            # embedding terms; these are covered by nothing, so drop them.
            # It costs about a quarter of five species and removes the only
            # photographs in the bank with no licence at all.
            if ALL_RIGHTS_RESERVED in credit.lower():
                restricted += 1
                continue
            if credit not in seen:
                seen[credit] = len(credits)
                credits.append(credit)

            ext = url.rsplit(".", 1)[-1]
            host = next((i for i, h in enumerate(INAT_HOSTS) if url.startswith(h)), None)
            flags = 16 if photo.get("mx") else 0
            if host is None or ext not in INAT_EXTS or "/photos/" not in url:
                rows.append([url, flags, photo.get("o") or 0, seen[credit]])
                continue
            try:
                pid = int(url.rsplit("/photos/", 1)[1].split("/", 1)[0])
            except (IndexError, ValueError):
                rows.append([url, flags, photo.get("o") or 0, seen[credit]])
                continue
            rows.append(
                [pid, flags + 8 * host + INAT_EXTS.index(ext), photo.get("o") or 0, seen[credit]]
            )
        if rows:
            species[code] = rows

    if restricted:
        print(f"  {restricted} iNaturalist photographs dropped: all rights reserved")

    return {"c": credits, "s": species}


def export_bank(cache: dict) -> tuple[int, int]:
    """Write the app's photo bank from every cache on disk plus this run's.

    Called at checkpoints, not only at the end. Until this file is written the
    quiz cannot ask about a species no matter how many photographs sit in the
    cache - the question pool is filtered by what has a picture.
    """
    merged: dict = {}
    for path in sorted(common.RAW.glob("photos_ml*.json")):
        # Our own cache is already in memory. Re-parsing it at every checkpoint
        # costs time and a second copy of the whole harvest for no new fact.
        if path == CACHE:
            continue
        try:
            for code, value in json.loads(path.read_text(encoding="utf-8")).items():
                if entry_photos(value):
                    merged[code] = value
        except (json.JSONDecodeError, OSError):
            continue  # mid-checkpoint rewrite; the in-memory copy still counts
    for code, value in cache.items():
        if entry_photos(value):
            merged[code] = value

    # Photographers repeat heavily across a species, so credits go in a shared
    # table and each photo carries an index into it.
    credits: list[str] = []
    seen: dict[str, int] = {}
    species: dict[str, list] = {}
    total = 0

    for code, value in sorted(merged.items()):
        rows = []
        for photo in entry_photos(value):
            who = photo.get("by") or ""
            if who not in seen:
                seen[who] = len(credits)
                credits.append(who)
            # meta packs three small facts into one integer, because the file
            # is otherwise mostly commas:
            #   bit 0      Mexican checklist
            #   bits 1-6   rating in tenths (25-50)
            #   bits 7+    plumage variant, indexed into plumage.VARIANTS
            tenths = int(round(float(photo.get("r") or 0) * 10))
            variant = photo.get("v") or "any"
            index = plumage.VARIANTS.index(variant) if variant in plumage.VARIANTS else 0
            meta = (1 if photo.get("mx") else 0) | (tenths << 1) | (index << 7)
            rows.append([photo["a"], meta, seen[who]])
        if rows:
            species[code] = rows
            total += len(rows)

    fallback = pack_inat()

    # A Macaulay bank this thin is not a bank: the app shows whichever source
    # wins outright, so one Macaulay photograph would mean the same picture
    # every single time that species came up. Where iNaturalist has more, hand
    # the species back to it rather than carry a Macaulay entry that blocks it.
    # (Elegant Trogon came back with one asset from an otherwise clean harvest,
    # which is how this was found.)
    MIN_ML = 10
    handed_back = sorted(
        code
        for code, rows in species.items()
        if len(rows) < MIN_ML and len(fallback["s"].get(code) or []) > len(rows)
    )
    for code in handed_back:
        total -= len(species.pop(code))
    if handed_back:
        print(
            f"  {len(handed_back)} species left to iNaturalist, too thin on Macaulay: "
            + ", ".join(handed_back)
        )

    # The iNaturalist block is a fallback, so carrying species Macaulay already
    # covers is pure weight - and it is half the file. Only the species with no
    # Macaulay photographs at all are kept. The full harvest stays in
    # data/raw/photos_inat.json, so widening this again is one resync away.
    dropped = len(fallback["s"]) - len(
        [c for c in fallback["s"] if c not in species]
    )
    fallback["s"] = {c: v for c, v in fallback["s"].items() if c not in species}
    used = {i for rows in fallback["s"].values() for _, _, _, i in rows}
    # Its credit table was built for the whole harvest; reindex to what is left.
    keep = sorted(used)
    remap = {old: new for new, old in enumerate(keep)}
    fallback["c"] = [fallback["c"][i] for i in keep]
    fallback["s"] = {
        c: [[a, f, o, remap[i]] for a, f, o, i in rows]
        for c, rows in fallback["s"].items()
    }
    if dropped:
        print(f"  iNaturalist fallback trimmed: {dropped} species already on Macaulay")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"ml": {"c": credits, "s": species}, "inat": fallback},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # Playable is the union: Macaulay where we have it, iNaturalist elsewhere.
    playable = set(species) | set(fallback["s"])
    return len(playable), total + sum(len(v) for v in fallback["s"].values())


def main() -> int:
    idx_path = common.ROOT / "src" / "lib" / "data" / "quiz" / "index.json"
    if not idx_path.exists():
        print("Run export_web.py first.")
        return 1

    index = json.loads(idx_path.read_text(encoding="utf-8"))
    args = sys.argv[1:]

    def read_cache() -> dict:
        return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    if "--sync" in args:
        # The cache is rewritten whole at each checkpoint, so a sync fired at
        # exactly the wrong moment reads a half-written file. That is a wait,
        # not an error: retry rather than overwrite the bank with nothing.
        for _ in range(5):
            try:
                cached = read_cache()
            except (json.JSONDecodeError, OSError):
                time.sleep(1.5)
                continue
            n, total = export_bank(cached)
            print(f"synced {OUT.relative_to(common.ROOT)}: {n} species, {total} photographs")
            return 0
        print("cache was being rewritten each time we looked - try again in a moment")
        return 1

    refresh = "--refresh" in args
    only = [a for a in args if not a.startswith("--")] or None
    if only:
        index = [e for e in index if e["c"] in only or e["n"] in only]
        print(f"limited to {len(index)} species")

    cache = read_cache()
    todo = [
        e
        for e in index
        if refresh or e["c"] not in cache or entry_want(cache[e["c"]]) < PER_SPECIES
    ]
    print(
        f"{len(cache)} cached, {len(todo)} to fetch, "
        f"{PER_SPECIES} photos each at {MIN_RATING}+ stars "
        f"(~{len(todo) * PAUSE * (1 if SINGLE_REQUEST else 2) / 60:.0f} min)"
    )

    wrong_taxon = 0
    strikes = 0
    i = 0
    # Which species this run actually got an answer about. Without this, a run
    # that was blocked on its first request reports every unfetched species as
    # "nothing at 2.5+ stars" - which reads as a fact about the birds when it is
    # only a fact about how far we got.
    attempted: set[str] = set()
    try:
        while i < len(todo):
            entry = todo[i]
            try:
                got, wrong, failed = fetch_species(entry["c"], PER_SPECIES)
            except Challenged:
                # Save first: a cooldown is a long time to hold work in memory
                # on a machine that kills processes for it.
                CACHE.write_text(json.dumps(cache), encoding="utf-8")
                export_bank(cache)
                strikes += 1
                if strikes >= GIVE_UP_AFTER:
                    print()
                    print(f"Challenged {strikes} times running. Stopping.")
                    print("The block is lasting hours, not minutes. What is cached is")
                    print("kept and the rest is not marked done, so a later run resumes.")
                    break
                print(f"    challenged - probing again in {COOLDOWN // 60} min "
                      f"({entry['n']}, attempt {strikes}/{GIVE_UP_AFTER})")
                time.sleep(COOLDOWN)
                continue  # same species, not the next one
            strikes = 0
            i += 1
            attempted.add(entry["c"])
            wrong_taxon += wrong
            had = len(entry_photos(cache.get(entry["c"])))

            # A request that errored is not evidence that a species has no
            # photographs. Writing {"w": 50, "p": []} for it marks the species
            # done and skips it on every later run - a network blip turned into
            # a permanent hole. Leave it uncached instead.
            if failed and not got:
                print(f"  [{i}/{len(todo)}] {entry['n']:34}  request failed - left uncached")
                continue

            # Never trade down. A flaky request that returns three photographs
            # must not throw away the forty we already had.
            if len(got) >= had:
                cache[entry["c"]] = {"w": PER_SPECIES, "p": got}
                stars = f"{sum(p['r'] for p in got) / len(got):.1f}*" if got else "  -"
                note = f"{len(got):3} photos  avg {stars}"
            else:
                cache[entry["c"]] = {
                    "w": PER_SPECIES,
                    "p": entry_photos(cache[entry["c"]]),
                }
                note = f"{len(got):3} photos  - kept the {had} we had"
            if wrong:
                note += f"  [{wrong} wrong-taxon skipped]"
            print(f"  [{i}/{len(todo)}] {entry['n']:34} {note}")

            # Two intervals, because the two jobs cost very differently and this
            # machine kills long runs for memory. Writing the cache is a little
            # I/O and is all that stands between a kill and lost work; repacking
            # the bank allocates, and being a rung behind costs nothing.
            if i % 10 == 0:
                CACHE.write_text(json.dumps(cache), encoding="utf-8")
            if i % 50 == 0:
                n, total = export_bank(cache)
                print(f"      checkpoint - {n} species, {total} photographs playable")
    except KeyboardInterrupt:
        print("\ninterrupted - saving what we have")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache), encoding="utf-8")

    n, total = export_bank(cache)
    counts = sorted(len(entry_photos(v)) for v in cache.values() if entry_photos(v))
    print()
    print(f"wrote {OUT.relative_to(common.ROOT)}: {n} species, {total} photographs")
    print(f"  {OUT.stat().st_size / 1048576:.1f} MB")
    if counts:
        print(f"  median {counts[len(counts) // 2]} per species, thinnest {counts[0]}")
        thin = sum(1 for c in counts if c < 10)
        if thin:
            print(f"  {thin} species under 10 photographs - these will repeat")
    unreached = [
        e for e in index if e["c"] not in attempted and not entry_photos(cache.get(e["c"]))
    ]
    if unreached:
        print(f"  {len(unreached)} species not reached this run - run again to continue")

    empty = [
        e["n"]
        for e in index
        if e["c"] in attempted and not entry_photos(cache.get(e["c"]))
    ]
    if empty:
        print(f"  {len(empty)} species have nothing at {MIN_RATING}+ stars:")
        for name in empty[:8]:
            print(f"    {name}")
        if len(empty) > 8:
            print(f"    ... and {len(empty) - 8} more")
    if wrong_taxon:
        print(f"  {wrong_taxon} records were the wrong taxon and were skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
