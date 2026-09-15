"""Import a Macaulay URL harvest (CSV) into the quiz's photo bank.

The harvester that produces the CSV is a separate tool - it collects asset ids
and credits, never image files. This script folds its output into
data/raw/photos_ml.json, which is the same cache fetch_photos.py writes, so the
existing packer and the app pick it up with no further changes.

Two things it fixes on the way in.

**The rating skew.** The harvester asks for exactly as many photographs as it
wants and takes them in rank order, so a run of 50 is the 50 best-rated: 87% of
the CSV sits at 4.5 stars or above. Those are the perched adult in golden hour,
which is the one bird nobody has trouble identifying. This samples across
rating bands instead of taking the top, so the quiz sees ordinary photographs
too. Sampling cannot invent spread that is not in the file - for that the
harvester needs to ask for a much larger pool than it keeps - but it stops the
bank being sorted best-first.

**The Mexican share.** The CSV's `region` column is empty, but `location` holds
a stringified dict with the country code in it, so the flag can be recovered
from there rather than lost.

    ~/anaconda3/python.exe quiz/pipeline/import_ml_csv.py macaulay_image_urls.csv
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import plumage  # noqa: E402

CACHE = common.RAW / "photos_ml.json"

# Same floor the harvester should be using: below about 2.5 stars a Macaulay
# photograph is a distant smudge, which teaches nothing but frustration.
MIN_RATING = 2.5

PER_SPECIES = 50

# Named variants get a smaller bank than the unfiltered one. Fifteen juvenile
# Cooper's Hawks is plenty to stop the same photograph recurring, and keeping
# them modest is what stops 477 species with variants tripling the file.
PER_VARIANT = 15

# `adult` is the exception, and gets the full bank. For a raptor or a gull the
# adult is not a niche plumage you occasionally drill - it is the default view
# of the bird, and the one the unfiltered bank was failing to give. Capping it
# at 15 would also throw away photographs we already hold: the adult search
# re-identifies assets already sitting in the `any` bank, and anything over the
# cap would be dropped from both.
PER_ADULT = PER_SPECIES

# Bands to sample evenly from, best last. Taking equal shares from each means a
# species with any spread at all contributes some ordinary photographs, not
# just its portfolio pieces.
BANDS = [(2.5, 3.5), (3.5, 4.25), (4.25, 4.7), (4.7, 5.01)]


def country_of(location: str) -> str:
    """Pull the country code out of the CSV's stringified location dict.

    The harvester writes Python's `repr` of a dict into the column, so this is
    a literal_eval rather than a JSON parse. Wrong-shaped values are common
    enough that a failure here means "unknown", not an error.
    """
    if not location or not location.startswith("{"):
        return ""
    try:
        value = ast.literal_eval(location)
    except (ValueError, SyntaxError):
        return ""
    return str(value.get("countryCode") or "") if isinstance(value, dict) else ""


def sample_across_bands(rows: list[dict], want: int) -> list[dict]:
    """Take `want` photographs spread over the rating bands, not off the top."""
    if len(rows) <= want:
        return rows

    buckets: list[list[dict]] = [[] for _ in BANDS]
    for row in rows:
        for i, (lo, hi) in enumerate(BANDS):
            if lo <= row["r"] < hi:
                buckets[i].append(row)
                break

    picked: list[dict] = []
    # Round-robin one from each non-empty band until full, so a thin band is
    # exhausted rather than allowed to cap the total.
    for bucket in buckets:
        random.shuffle(bucket)
    while len(picked) < want and any(buckets):
        for bucket in buckets:
            if not bucket or len(picked) >= want:
                continue
            picked.append(bucket.pop())
    return picked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="the harvester's macaulay_image_urls.csv")
    parser.add_argument("--per-species", type=int, default=PER_SPECIES)
    parser.add_argument("--per-variant", type=int, default=PER_VARIANT)
    parser.add_argument("--per-adult", type=int, default=PER_ADULT)
    parser.add_argument("--min-rating", type=float, default=MIN_RATING)
    parser.add_argument(
        "--top",
        action="store_true",
        help="take the best-rated instead of sampling across bands",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "discard the existing cache and build it from this CSV alone. "
            "Needed when the import should SHRINK a species, which the "
            "never-trade-down rule otherwise refuses"
        ),
    )
    args = parser.parse_args()

    path = Path(args.csv_path)
    if not path.exists():
        print(f"not found: {path}")
        return 1

    by_species: dict[str, list[dict]] = {}

    # Which searches returned an asset is the only per-asset tagging Macaulay
    # gives us - the CSV has no age or sex column - so the union across
    # searches is the record. An asset in both the immature search and the
    # flight search is an immature bird in flight, and keeping only one of
    # those, as this once did, throws away the half worth drilling.
    asset_tags: dict[tuple[str, int], set[str]] = {}
    total = skipped_rating = skipped_bad = 0

    # csv rather than pandas: the file is 33 MB and this only needs one pass.
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            total += 1
            code = (row.get("taxon") or "").strip().lower()
            asset = (row.get("asset_id") or "").strip()
            if not code or not asset.isdigit():
                skipped_bad += 1
                continue
            try:
                rating = round(float(row.get("rating") or 0), 2)
            except ValueError:
                skipped_bad += 1
                continue
            if rating < args.min_rating:
                skipped_rating += 1
                continue
            # Older harvests have no variant column at all; those rows are
            # the unfiltered search, which is what "any" means.
            found = (row.get("variant") or "any").strip().lower()
            if found in plumage.TAG_BIT:
                asset_tags.setdefault((code, int(asset)), set()).add(found)
            # Flight is not a plumage. Its search is unfiltered for age and sex,
            # so those rows belong in the unfiltered bank; the tag above is
            # what carries the fact that the bird was airborne.
            variant = found if found in plumage.VARIANTS else "any"
            photo = {
                "a": int(asset),
                "by": (row.get("photographer") or "").strip(),
                "l": (row.get("license") or "").strip(),
                "r": rating,
                "mx": country_of(row.get("location") or "") == "MX",
            }
            by_species.setdefault((code, variant), []).append(photo)

    print(f"read {total:,} rows from {path.name}")
    print(f"  {skipped_rating:,} below {args.min_rating} stars, {skipped_bad:,} unusable")
    print(f"  {len({c for c, _ in by_species}):,} species with at least one usable photograph")

    cache: dict = {}
    if CACHE.exists() and not args.rebuild:
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ! {CACHE.name} was unreadable; starting a fresh one")
    elif args.rebuild:
        print("  --rebuild: ignoring the existing cache")

    def held(code: str) -> int:
        value = cache.get(code)
        if isinstance(value, dict):
            return len(value.get("p") or [])
        return len(value or [])

    # One photograph can come back from several variant searches - a bird
    # tagged "immature" is also in the unfiltered results - so the same asset
    # would otherwise sit in two banks at once. That inflates the counts, makes
    # it twice as likely to be drawn, and labels it "immature" one time and
    # "any" the next. Keep the most specific tag for each asset and drop the
    # rest: a named variant tells us something, "any" tells us nothing.
    best_variant: dict[tuple[str, int], str] = {}
    for (code, variant), rows in by_species.items():
        for row in rows:
            key = (code, row["a"])
            # `held` would shadow the held() helper defined below.
            current = best_variant.get(key)
            if current is None:
                best_variant[key] = variant
            elif current == "any" and variant != "any":
                best_variant[key] = variant
            elif current != "any" and variant != "any":
                # Contradictory tagging, e.g. male and juvenile on one asset.
                # VARIANTS order is arbitrary but stable, so reruns agree.
                if plumage.VARIANTS.index(variant) < plumage.VARIANTS.index(current):
                    best_variant[key] = variant

    deduped = 0
    for (code, variant), rows in list(by_species.items()):
        kept = [r for r in rows if best_variant[(code, r["a"])] == variant]
        for row in kept:
            found = asset_tags.get((code, row["a"]))
            if found:
                row["t"] = sorted(found)
            row.pop("v", None)
        deduped += len(rows) - len(kept)
        if kept:
            by_species[(code, variant)] = kept
        else:
            del by_species[(code, variant)]
    if deduped:
        print(f"  {deduped:,} rows dropped as the same asset under another variant")

    # Cap each variant separately, then pool them per species.
    pooled: dict[str, list[dict]] = {}
    variant_counts: dict[str, int] = {}
    for (code, variant), rows in by_species.items():
        # Dedupe by asset: the same photograph can appear under several region
        # tiers in one harvest.
        unique = {row["a"]: row for row in rows}
        if variant == "any":
            want = args.per_species
        elif variant == "adult":
            want = args.per_adult
        else:
            want = args.per_variant
        chosen = (
            sorted(unique.values(), key=lambda r: -r["r"])[:want]
            if args.top
            else sample_across_bands(list(unique.values()), want)
        )
        chosen.sort(key=lambda r: -r["r"])
        pooled.setdefault(code, []).extend(chosen)
        variant_counts[variant] = variant_counts.get(variant, 0) + len(chosen)

    added = improved = kept = 0
    for code, chosen in pooled.items():
        # Never trade down: an import that would shrink a species leaves it be.
        before = held(code)
        if len(chosen) < before:
            kept += 1
            continue
        if before:
            improved += 1
        else:
            added += 1
        cache[code] = {"w": args.per_species, "p": chosen}

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache), encoding="utf-8")

    photos = sum(held(c) for c in cache)
    print()
    print(f"wrote {CACHE.relative_to(common.ROOT)}")
    print(f"  {added:,} species new, {improved:,} improved, {kept:,} left alone")
    print(f"  {len(cache):,} species, {photos:,} photographs in the cache")
    if len(variant_counts) > 1:
        print("  by variant: " + ", ".join(
            f"{k}={v:,}" for k, v in sorted(variant_counts.items())
        ))
    ratings = [p["r"] for v in cache.values() for p in (v.get("p") or [])]
    if ratings:
        ratings.sort()
        print(
            f"  ratings: min {ratings[0]:.2f}, "
            f"median {ratings[len(ratings) // 2]:.2f}, max {ratings[-1]:.2f}"
        )
    print()
    print("Now run: fetch_photos.py --sync   (packs it into the app's bank)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
