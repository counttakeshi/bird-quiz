"""Fetch regional status and Spanish names from the eBird API.

Needs a free key from https://ebird.org/api/keygen. Pass it as an argument or
set EBIRD_API_KEY:

    python quiz/pipeline/fetch_chiapas.py YOUR_KEY_HERE
    EBIRD_API_KEY=... python quiz/pipeline/fetch_chiapas.py

This does NOT narrow the quiz to Chiapas. It tags each species with the
tightest region it is recorded from, so the quiz can weight questions toward
birds you meet weekly without ever removing the ones you meet once a decade.
Vagrancy is real and concentrated in the migratory groups this quiz exists for;
a species you have trained yourself not to consider is one you will get wrong
when it finally turns up. Everything in the reference sheet stays in the pool.

Regions are ordered tightest first, so a species on several lists is labelled by
the smallest one containing it.

The key is only ever sent to api.ebird.org and is never written to disk.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

BASE = "https://api.ebird.org/v2"

# Tightest first. The label a species gets is the first list it appears on.
# Verified against /ref/region/list/subnational1/MX - Quintana Roo is MX-ROO,
# not the MX-QROO you would guess from the state's name.
REGIONS: list[tuple[str, str]] = [
    ("chiapas", "MX-CHP"),
    ("neighbouring", "MX-OAX"),
    ("neighbouring", "MX-TAB"),
    ("neighbouring", "MX-VER"),  # the migration corridor most vagrants arrive down
    ("yucatan", "MX-YUC"),
    ("yucatan", "MX-ROO"),
    ("yucatan", "MX-CAM"),
    ("guatemala", "GT"),
    ("belize", "BZ"),
]


def get(path: str, key: str, **params):
    r = requests.get(
        f"{BASE}/{path}",
        headers={"X-eBirdApiToken": key},
        params=params,
        timeout=60,
    )
    if r.status_code == 403:
        raise SystemExit("eBird rejected the key (403). Check it at ebird.org/api/keygen")
    r.raise_for_status()
    return r


def main() -> int:
    key = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("EBIRD_API_KEY", "")).strip()
    if not key:
        print(__doc__)
        return 1

    common.RAW.mkdir(parents=True, exist_ok=True)

    status: dict[str, str] = {}
    for label, region in REGIONS:
        # One bad region code should not throw away the regions already
        # fetched. Labels are additive, so a gap degrades a species to the
        # next-widest label rather than corrupting anything.
        try:
            codes = get(f"product/spplist/{region}", key).json()
        except requests.HTTPError as exc:
            print(f"  {region:8} SKIPPED - {exc.response.status_code} (bad region code?)")
            continue
        added = 0
        for code in codes:
            if code not in status:
                status[code] = label
                added += 1
        print(f"  {region:8} {len(codes):5} species, {added:5} newly labelled '{label}'")

    common.REGIONS_JSON.write_text(json.dumps(status), encoding="utf-8")
    print(f"\nregional status: {len(status)} species -> {common.REGIONS_JSON.name}")

    # Spanish names for the search box. The taxonomy endpoint returns every bird
    # on earth, so ask only for the codes in the reference sheet.
    sheet = common.load_mexico_sheet()
    wanted = sorted({r["species_code"] for r in sheet} | set(status))
    names: dict[str, str] = {}
    chunk = 200
    for i in range(0, len(wanted), chunk):
        rows = get(
            "ref/taxonomy/ebird",
            key,
            fmt="json",
            locale="es_MX",
            species=",".join(wanted[i : i + chunk]),
        ).json()
        for row in rows:
            code, name = row.get("speciesCode"), row.get("comName")
            if code and name:
                names[code] = name
        print(f"  names {min(i + chunk, len(wanted))}/{len(wanted)}")

    common.NAMES_ES_JSON.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    print(f"Spanish names: {len(names)} -> {common.NAMES_ES_JSON.name}")
    print("\nNow rerun: build_traits.py, score_confusion.py, export_web.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
