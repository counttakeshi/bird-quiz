"""Which photo variants each species needs.

Reads data/plumage_classes.csv - family defaults with species overrides.

    ~/anaconda3/python.exe quiz/pipeline/plumage.py
    ~/anaconda3/python.exe quiz/pipeline/plumage.py --list Accipitridae
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

CLASSES = common.DATA / "plumage_classes.csv"

# Must match VARIANT_FILTERS in the harvester and VARIANTS in
# src/lib/quiz/pins.ts. The order is the wire format's variant index, so
# appending is safe and reordering is not - which is why `adult` sits at the
# end rather than next to the other ages. The app has its own display order.
VARIANTS = ["any", "male", "female", "juvenile", "immature", "adult"]

# Not a plumage, so not in VARIANTS: a bird can be both juvenile and in flight,
# and for a raptor that combination is the whole point.
FLIGHT = "flight"

# What a photograph can be tagged with, one bit each, starting at bit 7 of the
# packed record. A bit rather than an index because these are not alternatives:
# an asset returned by both the immature search and the flight search is an
# immature bird in flight, and the old format could only record one of the two.
# Append only - the position is the wire format.
TAGS = ["male", "female", "juvenile", "immature", "adult", FLIGHT]
TAG_BIT = {name: 7 + i for i, name in enumerate(TAGS)}


def tags_of(search: str) -> set[str]:
    """What a Macaulay search name says about the photographs it returned.

    A search is named for the filters it carried, so `flight-immature` is the
    flight behaviour and the immature age at once. Splitting on the hyphen
    keeps the harvester free to add combinations without this having to learn
    each one.
    """
    return {part for part in (search or "").split("-") if part in TAG_BIT}


class Plumage:
    """Per-species sex, age and flight flags, resolved from family defaults."""

    def __init__(self, families: dict, species: dict) -> None:
        self.families = families
        self.species = species

    def flags(self, code: str, family: str) -> dict[str, bool]:
        """Family row, with any column the species row actually sets on top.

        A species row overrides column by column rather than wholesale, so a
        blank cell inherits. Writing `yes` or `no` still overrides, which is
        what every row written before the flight column did - and why that
        column had to inherit rather than default to no. Eight raptors carried
        an override for their ages and would otherwise have quietly lost the
        flight search their family asks for, among them Northern Harrier and
        Cooper's Hawk.
        """
        out = dict(self.families.get(family, {}))
        for key, value in self.species.get(code, {}).items():
            if value is not None:
                out[key] = value
        return {k: bool(out.get(k)) for k in ("sexes", "ages", "flight")}

    def variants_for(self, code: str, family: str) -> list[str]:
        """The variants worth harvesting for this species.

        `any` is always first and is not an adult-only search - it is simply
        the best-rated photographs of the species, whatever they show, so for
        a raptor it holds plenty of untagged juveniles. The filtered variants
        are additions to it, never replacements, because age and sex tagging
        is optional on upload and sparse for most species.

        `flight` is orthogonal to both: it asks Macaulay for the "Flying"
        behaviour with no age or sex filter, because a bird overhead is the one
        case where you usually cannot tell either.

        Where ages differ, `adult` is collected too - but only if the sexes
        look alike. Macaulay's male and female searches are both sent with
        age=adult, so where the sexes differ those banks already are the adult
        deck and a separate `adult` request buys almost nothing. Where they
        look alike there is nothing to borrow from, and without an adult tier
        the quiz can drill young birds but cannot exclude them.
        """
        flags = self.flags(code, family)
        out = ["any"]
        if flags["sexes"]:
            out += ["male", "female"]
        if flags["ages"]:
            if not flags["sexes"]:
                out.append("adult")
            out += ["juvenile", "immature"]
        if flags["flight"]:
            out.append(FLIGHT)
        return out


def load() -> Plumage:
    if not CLASSES.exists():
        print(f"  (no {CLASSES.name}; no species will get variants)")
        return Plumage({}, {})

    families: dict[str, dict[str, bool | None]] = {}
    species: dict[str, dict[str, bool | None]] = {}

    with CLASSES.open(encoding="utf-8", newline="") as fh:
        # The file carries a long comment header, which csv has no concept of.
        rows = (line for line in fh if not line.lstrip().startswith("#"))
        for row in csv.DictReader(rows):
            scope = (row.get("scope") or "").strip()
            key = (row.get("key") or "").strip()
            if not scope or not key:
                continue
            # None, not False, for a blank cell: a species row has to be able
            # to say nothing about a column and inherit the family's answer.
            def flag(name: str) -> bool | None:
                raw = (row.get(name) or "").strip().lower()
                return None if raw == "" else raw == "yes"

            flags = {
                "sexes": flag("sexes"),
                "ages": flag("ages"),
                "flight": flag("flight"),
            }
            if scope == "family":
                families[key] = flags
            elif scope == "species":
                species[key] = flags

    return Plumage(families, species)


def traits() -> dict[str, dict]:
    path = common.TAXONOMY_CSV
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["species_code"]: r for r in csv.DictReader(fh)}


def bank() -> dict[str, dict[str, int]]:
    """What the app's photo bank actually holds, per species and variant.

    Decoded from the packed wire format the same way src/lib/quiz/photos.ts
    does it, so this reports what the quiz will really offer rather than what
    the rules below asked for. The two differ: Macaulay's taggers use
    `immature` for raptors far more than `juvenile`, and plenty of species have
    no sexed photographs at all.
    """
    path = common.ROOT / "src" / "lib" / "data" / "quiz" / "photos.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, int]] = {}
    for code, packed in (data.get("ml") or {}).get("s", {}).items():
        counts: dict[str, int] = {}
        for row in packed:
            hit = False
            for name, bit in TAG_BIT.items():
                if (row[1] >> bit) & 1:
                    counts[name] = counts.get(name, 0) + 1
                    hit = True
            if not hit:
                counts["any"] = counts.get("any", 0) + 1
        out[code] = counts
    for code, packed in (data.get("inat") or {}).get("s", {}).items():
        out.setdefault(code, {})["any"] = out.get(code, {}).get("any", 0) + len(packed)
    return out


def report_bank(plumage: Plumage, rows: dict[str, dict], family: str | None) -> int:
    held = bank()
    if not held:
        print("no photos.json - run fetch_photos.py --sync first")
        return 1

    print(f"{len(held)} species in the bank")
    print()
    print(f"{'variant':<12}{'photos':>9}{'species':>10}")
    for variant in ["any"] + TAGS:
        total = sum(c.get(variant, 0) for c in held.values())
        count = sum(1 for c in held.values() if c.get(variant))
        print(f"{variant:<12}{total:>9,}{count:>10,}")

    # A sexed bird is an adult - Macaulay's male and female searches are both
    # sent with age=adult - so the app counts those toward the adult deck. The
    # stored `adult` row above is only what was harvested under that name; this
    # is what the quiz will actually offer.
    eff_photos = sum(
        c.get("adult", 0) + c.get("male", 0) + c.get("female", 0) for c in held.values()
    )
    eff_species = sum(
        1 for c in held.values() if c.get("adult") or c.get("male") or c.get("female")
    )
    print(f"{'adult (effective)':<12}{eff_photos:>9,}{eff_species:>10,}")
    print("  ^ adult + male + female: a bird sexed in the field is an adult")

    withv = [c for c, v in held.items() if any(v.get(x) for x in VARIANTS[1:])]
    print()
    print(f"{len(withv)} species have a sex or age bank, {len(held) - len(withv)} have only 'any'")
    print("Only those with more than one variant show the pill row on /quiz.")

    # The species an adult harvest would still help: ages differ, sexes do not,
    # so nothing implies an adult and none was collected.
    need = []
    for code, row in rows.items():
        if code not in held:
            continue
        counts = held[code]
        if counts.get("adult") or counts.get("male") or counts.get("female"):
            continue
        if counts.get("juvenile") or counts.get("immature"):
            need.append((row["family"], row["common_name"]))
    print()
    print(f"{len(need)} species have young birds but no adult deck - these are what an")
    print("adult harvest would fix (ages differ, sexes look alike):")
    fams: dict[str, int] = {}
    for fam, _ in need:
        fams[fam] = fams.get(fam, 0) + 1
    for fam, n in sorted(fams.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {fam:<20} {n}")

    # Where the rules and the bank disagree: the interesting list, because it
    # is what a re-harvest would fix.
    missing = []
    for code, row in rows.items():
        if code not in held:
            continue
        wanted = set(plumage.variants_for(code, row["family"])) - {"any"}
        if wanted and not any(held[code].get(v) for v in wanted):
            missing.append((row["family"], row["common_name"], sorted(wanted)))
    print()
    print(f"{len(missing)} species the rules wanted variants for but the harvest found none:")
    for fam, name, wanted in sorted(missing)[:15]:
        print(f"  {fam:<18} {name:<32} wanted {', '.join(wanted)}")
    if len(missing) > 15:
        print(f"  ... and {len(missing) - 15} more")

    if family:
        print()
        print(f"{family}:")
        for code, row in sorted(rows.items(), key=lambda kv: kv[1]["common_name"]):
            if row["family"] != family or code not in held:
                continue
            counts = held[code]
            have = ", ".join(f"{v} {counts[v]}" for v in VARIANTS if counts.get(v))
            print(f"  {code:<10} {row['common_name']:<34} {have}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", metavar="FAMILY", help="show one family's species")
    parser.add_argument(
        "--bank",
        action="store_true",
        help="report what photos.json actually holds, not what the rules want",
    )
    args = parser.parse_args()

    plumage = load()
    rows = traits()

    if args.bank:
        if not rows:
            print("no taxonomy.csv - run export_web.py first")
            return 1
        return report_bank(plumage, rows, args.list)
    if not rows:
        print("no taxonomy.csv - run export_web.py first")
        return 1

    print(f"{len(plumage.families)} family rules, {len(plumage.species)} species overrides")
    print()

    sexes = ages = both = neither = 0
    requests = 0
    for code, row in rows.items():
        flags = plumage.flags(code, row["family"])
        if flags["sexes"] and flags["ages"]:
            both += 1
        elif flags["sexes"]:
            sexes += 1
        elif flags["ages"]:
            ages += 1
        else:
            neither += 1
        requests += len(plumage.variants_for(code, row["family"]))

    print(f"  sexes only   {sexes:5}")
    print(f"  ages only    {ages:5}")
    print(f"  both         {both:5}")
    print(f"  neither      {neither:5}")
    print(f"  ---")
    print(f"  {len(rows)} species -> {requests} variant searches")
    print(f"  ({requests - len(rows)} more than a plain one-bank harvest)")

    if args.list:
        print()
        print(f"{args.list}:")
        for code, row in sorted(rows.items(), key=lambda kv: kv[1]["common_name"]):
            if row["family"] != args.list:
                continue
            variants = plumage.variants_for(code, row["family"])
            mark = " (override)" if code in plumage.species else ""
            print(f"  {code:10} {row['common_name']:34} {', '.join(variants)}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
