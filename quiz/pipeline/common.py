"""Shared paths and helpers for the quiz pipeline."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUIZ = ROOT / "quiz"
DATA = QUIZ / "data"
RAW = DATA / "raw"

SPECIES_TS = ROOT / "src" / "lib" / "data" / "species.ts"
MEXICO_XLSX = Path.home() / "Documents" / "Bird Taxon Codes Reference.xlsx"

REGIONS_JSON = RAW / "regions.json"
NAMES_ES_JSON = RAW / "names_es.json"
TAXONOMY_CSV = DATA / "taxonomy.csv"

# Family header rows in the Mexico spreadsheet, not species.
NOT_SPECIES = {"Aramidae", "Pandionidae", "Peucedramidae", "Icteriidae"}


def genus(sci: str) -> str:
    return sci.split()[0] if sci else ""


def load_mexico_sheet() -> list[dict]:
    """The Mexico reference sheet, in eBird taxonomic order."""
    import pandas as pd

    df = pd.read_excel(MEXICO_XLSX)
    rows = []
    for _, r in df.iterrows():
        sci = str(r["scientific name"]).strip()
        if not sci or sci in NOT_SPECIES:
            continue
        rows.append(
            {
                "sort": int(r["sort v2024"]),
                "species_code": str(r["species_code"]).strip(),
                "common_name": str(r["English name"]).strip(),
                "scientific_name": sci,
            }
        )
    rows.sort(key=lambda r: r["sort"])
    return rows


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
