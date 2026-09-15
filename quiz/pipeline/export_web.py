"""Write the species index the quiz loads.

One output: src/lib/data/quiz/index.json — every species with its codes, names
and taxonomy. Genus is taken from the scientific name; family is carried
through so the quiz can suggest related species to compare.

    ~/anaconda3/python.exe quiz/pipeline/export_web.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

OUT = common.ROOT / "src" / "lib" / "data" / "quiz" / "index.json"
TAXONOMY = common.DATA / "taxonomy.csv"


def spanish() -> dict[str, str]:
    path = common.NAMES_ES_JSON
    if not path.exists():
        print("  (no Spanish names - run fetch_chiapas.py with an API key)")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def regions() -> dict[str, str]:
    path = common.REGIONS_JSON
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if not TAXONOMY.exists():
        print(f"missing {TAXONOMY.relative_to(common.ROOT)}")
        return 1

    es, region = spanish(), regions()
    index = []

    with TAXONOMY.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("species_code") or "").strip()
            sci = (row.get("scientific_name") or "").strip()
            if not code or not sci:
                continue
            entry = {"c": code, "n": (row.get("common_name") or "").strip(), "s": sci}
            if es.get(code):
                entry["e"] = es[code]
            if row.get("slug"):
                entry["slug"] = row["slug"].strip()
            if region.get(code):
                entry["r"] = region[code]
            if row.get("family"):
                entry["f"] = row["family"].strip()
            entry["g"] = sci.split()[0]
            index.append(entry)

    index.sort(key=lambda e: e["n"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    print(f"wrote {OUT.relative_to(common.ROOT)}: {len(index)} species")
    print(f"  {sum(1 for e in index if 'e' in e)} with Spanish names")
    print(f"  {len({e['f'] for e in index if 'f' in e})} families, "
          f"{len({e['g'] for e in index})} genera")
    print(f"  {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
