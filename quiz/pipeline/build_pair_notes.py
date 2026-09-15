"""Generate pair notes from a structural trait table.

Reads data/empid_traits.csv and writes a note for every pair, naming what
differs, most diagnostic mark first.

    ~/anaconda3/python.exe quiz/pipeline/build_pair_notes.py
    ~/anaconda3/python.exe quiz/pipeline/build_pair_notes.py --show aldfly wilfly

Existing notes are never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

TRAITS = common.DATA / "empid_traits.csv"
NOTES = common.ROOT / "src" / "lib" / "data" / "quiz" / "pair_notes.json"

# Ordered by how much the mark is worth in the field, best first. The generated
# note follows this order, so the thing to look at first is named first.
#
# Each entry is (column, how to phrase it, ordered scale or None for free text).
AXES: list[tuple[str, str, list[str] | None]] = [
    ("projection", "primary projection", ["short", "medium", "long"]),
    ("eyering", "eye-ring", ["indistinct", "messy", "crisp", "teardrop"]),
    ("mandible", "lower mandible", ["dark", "partial", "orange"]),
    ("contrast", "upper/underpart contrast", ["weak", "medium", "strong"]),
    ("wingpanel", "wing panel contrast", ["weak", "medium", "strong"]),
    ("wingbar", "wingbar contrast", ["weak", "medium", "strong"]),
    ("tail_length", "tail length", ["short", "medium", "long"]),
    ("tail_width", "tail width", ["narrow", "medium", "wide"]),
    ("forehead", "forehead angle", ["shallow", "intermediate", "steep"]),
    ("crown", "crown", None),
    ("bill", "bill", ["small", "medium", "long"]),
    ("colour", "overall colour", None),
]

# Below this many differing marks the pair is genuinely hard, and the note says
# so rather than pretending three weak marks add up to an identification.
FEW = 3


def load_traits() -> list[dict]:
    with TRAITS.open(encoding="utf-8", newline="") as fh:
        rows = (line for line in fh if not line.lstrip().startswith("#"))
        return [r for r in csv.DictReader(rows) if (r.get("code") or "").strip()]


def short(name: str) -> str:
    """'Alder Flycatcher' -> 'Alder'. The genus is not the news."""
    for suffix in (" Flycatcher", " Wood-Pewee", " Pewee"):
        if name.endswith(suffix) and name != suffix.strip():
            return name[: -len(suffix)]
    return name


def compare(a: dict, b: dict) -> list[str]:
    """Phrase every axis on which the two differ, most diagnostic first."""
    lines = []
    for column, label, scale in AXES:
        left, right = (a.get(column) or "").strip(), (b.get(column) or "").strip()
        if not left or not right or left == right:
            continue
        if scale and left in scale and right in scale:
            # An ordered scale can be phrased as a direction, which is how you
            # actually use it: "longer", not "long versus medium".
            higher, lower = (a, b) if scale.index(left) > scale.index(right) else (b, a)
            hv = left if higher is a else right
            lv = right if higher is a else left
            lines.append(f"{label}: {short(higher['name'])} {hv}, {short(lower['name'])} {lv}")
        else:
            lines.append(f"{label}: {short(a['name'])} {left}, {short(b['name'])} {right}")
    return lines


def note_for(a: dict, b: dict) -> str:
    marks = compare(a, b)
    parts: list[str] = []

    if not marks:
        parts.append(
            f"{short(a['name'])} and {short(b['name'])} score the same on every "
            "structural mark. Go by voice."
        )
    else:
        if len(marks) <= FEW:
            parts.append("A close pair - few marks separate them, so take all of them together.")
        parts.extend(marks)

    # Behaviour and voice are not scored on a scale, so they are appended whole
    # rather than diffed. Both are often the thing that settles it.
    for column, label in (("habit", "Behaviour"), ("voice", "Voice")):
        left, right = (a.get(column) or "").strip(), (b.get(column) or "").strip()
        if left and right and left != right:
            parts.append(f"{label} — {short(a['name'])}: {left}. {short(b['name'])}: {right}")

    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", nargs=2, metavar=("A", "B"), help="print one pair and stop")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace existing notes instead of keeping what is already there",
    )
    args = parser.parse_args()

    if not TRAITS.exists():
        print(f"no {TRAITS.name}")
        return 1

    rows = load_traits()
    by_code = {r["code"]: r for r in rows}
    print(f"{len(rows)} species in {TRAITS.name}")

    if args.show:
        a, b = (by_code.get(c) for c in args.show)
        if not a or not b:
            print(f"unknown code: {args.show}")
            return 1
        print()
        print(f"=== {a['name']} vs {b['name']} ===")
        print(note_for(a, b))
        return 0

    existing: dict = {}
    if NOTES.exists():
        try:
            existing = json.loads(NOTES.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ! {NOTES.name} unreadable; starting fresh")

    written = kept = 0
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            key = "|".join(sorted((a["code"], b["code"])))
            if key in existing and not args.overwrite:
                kept += 1
                continue
            existing[key] = note_for(a, b)
            written += 1

    NOTES.parent.mkdir(parents=True, exist_ok=True)
    NOTES.write_text(json.dumps(existing, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8")

    print(f"wrote {NOTES.relative_to(common.ROOT)}")
    print(f"  {written} pair notes generated, {kept} left as they were")
    print(f"  {len(existing)} notes in the file, {NOTES.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
