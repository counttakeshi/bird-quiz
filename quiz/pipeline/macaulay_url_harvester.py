from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

import pandas as pd

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ============================================================
# CONFIGURATION
# ============================================================

MACAULAY_ORIGIN = "https://search.macaulaylibrary.org"
MACAULAY_SEARCH_URL = f"{MACAULAY_ORIGIN}/catalog"
MACAULAY_API_URL = f"{MACAULAY_ORIGIN}/api/v2/search"

IMAGE_CDN_HOST = "cdn.download.ams.birds.cornell.edu"

ASSET_PATTERN = re.compile(
    r"asset[/=\"':\s]{1,3}(\d{6,})",
    re.IGNORECASE,
)

DEFAULT_IMAGES_PER_SPECIES = 50
DEFAULT_ASSET_SIZE = "1200"
DEFAULT_THUMB_SIZE = "320"
DEFAULT_DELAY = 0.3
DEFAULT_PAGE_TIMEOUT = 30
DEFAULT_MORE_CLICKS = 10

# How long to sit waiting for a human check to be cleared.
DEFAULT_CHECK_TIMEOUT = 600

# Cheap, always-populated taxon used to test the session.
PROBE_TAXON = "norcar"

# Plumage variants. "any" is unfiltered: it is NOT a male-only
# search, it is simply the best-rated photos of the species.
# Age and sex tagging is optional on upload, so the filtered
# variants return nothing at all for many species.
VARIANT_FILTERS = {
    "any": {},
    "male": {"sex": "male", "age": "adult"},
    "female": {"sex": "female", "age": "adult"},
    "adult": {"age": "adult"},
    "juvenile": {"age": "juvenile"},
    "immature": {"age": "immature"},
    # Macaulay's "Flying" behaviour. Deliberately unfiltered for age and sex:
    # a bird overhead is the one case where you usually cannot tell either, so
    # narrowing it would throw away most of the useful photographs.
    "flight": {"tag": "flying_flight"},
}

DEFAULT_VARIANTS = ["any", "male", "female", "juvenile"]

# ============================================================
# WHICH VARIANTS ARE WORTH ASKING FOR
# ============================================================
#
# "female"  -> sexes differ enough that a female image earns its
#              place. Implies the male image is worth having too.
# "age"     -> which age tag to ask for, or None to skip age
#              entirely. "immature" suits groups that take years to
#              mature and get tagged that way (raptors, gulls,
#              herons). "juvenile" suits passerines.
# "flight"  -> you see this bird overhead rather than perched, so a
#              flight photograph is the ordinary view and not a lucky
#              one. Independent of sex and age: the flight search is
#              sent unfiltered, because a bird overhead is the case
#              where you usually cannot tell either.
#
# Family is the default. Genus overrides it, for families that are
# not internally consistent. Anything not listed falls back to
# DEFAULT_RULE, which asks for everything and lets the Macaulay
# tag-count threshold do the pruning.

DEFAULT_RULE = {"female": True, "age": "juvenile"}

FAMILY_RULES: dict[str, dict[str, Any]] = {

    # --- non-passerines, sexes alike, age matters -------------
    "Accipitridae": {"female": False, "age": "immature", "flight": True},
    "Falconidae": {"female": False, "age": "immature", "flight": True},
    "Pandionidae": {"female": False, "age": "immature", "flight": True},
    "Laridae": {"female": False, "age": "immature"},
    "Ardeidae": {"female": False, "age": "immature"},
    "Threskiornithidae": {"female": False, "age": "immature"},
    "Ciconiidae": {"female": False, "age": "immature"},
    "Pelecanidae": {"female": False, "age": "immature"},
    "Sulidae": {"female": False, "age": "immature"},
    "Phalacrocoracidae": {"female": False, "age": "immature"},
    "Cathartidae": {"female": False, "age": "immature", "flight": True},
    "Scolopacidae": {"female": False, "age": "juvenile"},
    "Charadriidae": {"female": False, "age": "juvenile"},
    "Jacanidae": {"female": False, "age": "juvenile"},
    "Rallidae": {"female": False, "age": "juvenile"},

    # --- non-passerines, sexes differ -------------------------
    "Anatidae": {"female": True, "age": "immature"},
    "Fregatidae": {"female": True, "age": "immature"},
    "Anhingidae": {"female": True, "age": "immature"},
    "Odontophoridae": {"female": True, "age": None},
    "Trochilidae": {"female": True, "age": None},
    "Trogonidae": {"female": True, "age": None},
    "Alcedinidae": {"female": True, "age": None},
    "Picidae": {"female": True, "age": None},
    "Caprimulgidae": {"female": True, "age": None},
    "Galbulidae": {"female": True, "age": None},

    # --- non-passerines, sexes alike, age unhelpful -----------
    "Tinamidae": {"female": False, "age": None},
    "Cracidae": {"female": False, "age": None},
    "Columbidae": {"female": False, "age": None},
    "Cuculidae": {"female": False, "age": None},
    "Strigidae": {"female": False, "age": None},
    "Tytonidae": {"female": False, "age": None},
    "Nyctibiidae": {"female": False, "age": None},
    "Apodidae": {"female": False, "age": None, "flight": True},
    "Momotidae": {"female": False, "age": None},
    "Bucconidae": {"female": False, "age": None},
    "Ramphastidae": {"female": False, "age": None},
    "Psittacidae": {"female": False, "age": None},
    "Eurypygidae": {"female": False, "age": None},
    "Heliornithidae": {"female": False, "age": None},
    "Recurvirostridae": {"female": False, "age": None},
    "Burhinidae": {"female": False, "age": None},

    # --- passerines, sexes differ -----------------------------
    "Thamnophilidae": {"female": True, "age": None},
    "Cotingidae": {"female": True, "age": "immature"},
    "Pipridae": {"female": True, "age": "immature"},
    "Tityridae": {"female": True, "age": None},
    "Parulidae": {"female": True, "age": "immature"},
    "Cardinalidae": {"female": True, "age": "immature"},
    "Thraupidae": {"female": True, "age": "immature"},
    "Fringillidae": {"female": True, "age": None},
    "Ptiliogonatidae": {"female": True, "age": None},
    "Passeridae": {"female": True, "age": None},
    "Icteridae": {"female": True, "age": "immature"},

    # --- passerines, sexes alike ------------------------------
    "Tyrannidae": {"female": False, "age": None},
    "Furnariidae": {"female": False, "age": None},
    "Dendrocolaptidae": {"female": False, "age": None},
    "Formicariidae": {"female": False, "age": None},
    "Grallariidae": {"female": False, "age": None},
    "Rhinocryptidae": {"female": False, "age": None},
    "Vireonidae": {"female": False, "age": None},
    "Corvidae": {"female": False, "age": None},
    "Hirundinidae": {"female": False, "age": None, "flight": True},
    "Troglodytidae": {"female": False, "age": None},
    "Polioptilidae": {"female": False, "age": None},
    "Turdidae": {"female": False, "age": "juvenile"},
    "Mimidae": {"female": False, "age": None},
    "Cinclidae": {"female": False, "age": None},
    "Certhiidae": {"female": False, "age": None},
    "Sittidae": {"female": False, "age": None},
    "Regulidae": {"female": False, "age": None},
    "Bombycillidae": {"female": False, "age": None},
    "Motacillidae": {"female": False, "age": None},
    "Passerellidae": {"female": False, "age": None},
    "Peucedramidae": {"female": True, "age": None},
}

GENUS_RULES: dict[str, dict[str, Any]] = {

    # --- Icteridae, which the family default gets wrong -------
    "Icterus": {"female": True, "age": "immature"},
    "Quiscalus": {"female": True, "age": "immature"},
    "Agelaius": {"female": True, "age": "immature"},
    "Molothrus": {"female": True, "age": "juvenile"},
    "Xanthocephalus": {"female": True, "age": "immature"},
    "Leistes": {"female": True, "age": None},
    "Psarocolius": {"female": False, "age": None},
    "Cacicus": {"female": False, "age": None},
    "Amblycercus": {"female": False, "age": None},
    "Dives": {"female": False, "age": None},
    "Sturnella": {"female": False, "age": None},

    # --- other families that are not internally consistent ----
    "Dendrocygna": {"female": False, "age": None},
    "Penelopina": {"female": True, "age": None},
    "Circus": {"female": True, "age": "immature"},
    "Falco": {"female": True, "age": "immature"},
    "Phaethornis": {"female": False, "age": None},
    "Tangara": {"female": False, "age": None},
    "Chlorospingus": {"female": False, "age": None},
    "Saltator": {"female": False, "age": None},
    "Sporophila": {"female": True, "age": "immature"},
    "Piranga": {"female": True, "age": "immature"},
    "Habia": {"female": True, "age": None},
    "Ramphocelus": {"female": True, "age": "immature"},
    "Euphonia": {"female": True, "age": None},
    "Pheucticus": {"female": True, "age": "immature"},
    "Passerina": {"female": True, "age": "immature"},
    "Cyanocompsa": {"female": True, "age": "immature"},
    "Cyanerpes": {"female": True, "age": None},
    "Dacnis": {"female": True, "age": None},
    "Chlorophanes": {"female": True, "age": None},
    "Myioborus": {"female": False, "age": None},
    "Basileuterus": {"female": False, "age": None},
    "Chiroxiphia": {"female": True, "age": "immature"},
    "Manacus": {"female": True, "age": "immature"},
    "Cotinga": {"female": True, "age": "immature"},
    "Pachyramphus": {"female": True, "age": None},
    "Tityra": {"female": True, "age": None},
    "Dendrortyx": {"female": False, "age": None},
    "Herpetotheres": {"female": False, "age": None},
    "Micrastur": {"female": False, "age": "immature"},
}

# A variant is kept only if Macaulay has at least this many tagged
# photos for it. Tag density is itself a decent proxy for whether
# the plumage is distinct enough that anyone bothered to label it.
DEFAULT_VARIANT_THRESHOLD = 8

EBIRD_TAXONOMY_URL = (
    "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=csv&locale=en"
)

# Anchored to the repo, not to the working directory. Every one of these used
# to be a bare relative name, so running the harvester from anywhere but the
# repo root scattered the state file, the CSV and 180 MB of diagnostics into
# whatever folder the shell happened to be sitting in - and a state file the
# next run cannot find means the next run starts from scratch.
ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TAXONOMY_CACHE = str(ROOT / "ebird_taxonomy.csv")
DEFAULT_EXCEL_EXPORT = str(ROOT / "Bird Taxon Codes Reference (variants).xlsx")
DEFAULT_RULES_EXPORT = str(ROOT / "variant_rules_applied.csv")


# Region tiers, searched in order until the quota is filled.
# An empty string means no region filter, i.e. worldwide.
DEFAULT_REGION_TIERS = ["MX-CHP", "MX", ""]

DEFAULT_REFERENCE_FILE = (
    r"C:\Users\52967\Documents\Bird Taxon Codes Reference.xlsx"
)

# ------------------------------------------------------------
# eBird API key. Pass it as --ebird-key or set EBIRD_API_KEY in
# the environment; generate one at https://ebird.org/api/keygen
# while signed in. Only needed for the first run: the taxonomy
# is cached to ebird_taxonomy.csv afterwards.
#
# Left empty on purpose. This repo is published to GitHub Pages,
# and a key committed here would be public and permanent - git
# history keeps it even after a later deletion.
# ------------------------------------------------------------

EBIRD_API_KEY = ""

DEFAULT_STATE_FILE = str(ROOT / "macaulay_url_state.json")
DEFAULT_URL_EXPORT = str(ROOT / "macaulay_image_urls.csv")
DEFAULT_DIAGNOSTIC_DIRECTORY = str(ROOT / "macaulay_diagnostics")

EXPORT_EVERY = 25

# Saving the state file costs about six seconds, because it is rewritten whole.
# Doing that per species is most of the wall time on a resumed run, so batch it.
# A hard kill loses at most this many species of work, and they are re-fetchable;
# a normal exit or Ctrl-C still flushes through the finally block.
SAVE_EVERY = 10


# ============================================================
# BROWSER-SIDE SCRIPTS
# ============================================================

# The catalog's own XHR, issued from inside the page so that it
# carries the session cookies and Chrome's TLS fingerprint.
API_FETCH_SCRIPT = r"""
    const url = arguments[0];
    const done = arguments[arguments.length - 1];

    fetch(url, {
        credentials: "include",
        headers: { "Accept": "application/json" }
    })
        .then((response) => {
            return response.text().then((text) => {
                done({
                    ok: response.ok,
                    status: response.status,
                    body: text
                });
            });
        })
        .catch((error) => {
            done({ ok: false, status: 0, error: String(error) });
        });
"""

# Fallback: scrape whatever the rendered grid exposes.
HARVEST_SCRIPT = r"""
    const found = [];

    const push = (value) => {
        if (value) {
            found.push(String(value));
        }
    };

    const attributes = [
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "srcset",
        "data-srcset",
        "href"
    ];

    document.querySelectorAll("img, source, a[href]").forEach((element) => {
        attributes.forEach((name) => {
            push(element.getAttribute(name));
        });
    });

    document.querySelectorAll(
        "[data-asset-id], [data-assetid], [data-ml-asset-id]"
    ).forEach((element) => {
        push("asset/" + (
            element.getAttribute("data-asset-id") ||
            element.getAttribute("data-assetid") ||
            element.getAttribute("data-ml-asset-id")
        ));
    });

    return found;
"""


# ============================================================
# HARVESTER
# ============================================================

class MacaulayUrlHarvester:
    """
    Collects Macaulay image URLs and credit metadata. Downloads
    nothing: an asset ID is all that is needed to build every URL
    the archive serves for that photo.

    Primary route is the catalog's search API, called from inside
    a live Chrome page. The rendered-grid scraper is kept as a
    fallback for when the API shape changes.
    """

    def __init__(
        self,
        reference_file: str,
        state_file: str = DEFAULT_STATE_FILE,
        url_export: str = DEFAULT_URL_EXPORT,
        diagnostic_dir: str = DEFAULT_DIAGNOSTIC_DIRECTORY,
        target_images: int = DEFAULT_IMAGES_PER_SPECIES,
        asset_size: str = DEFAULT_ASSET_SIZE,
        thumb_size: str = DEFAULT_THUMB_SIZE,
        delay: float = DEFAULT_DELAY,
        page_timeout: int = DEFAULT_PAGE_TIMEOUT,
        more_clicks: int = DEFAULT_MORE_CLICKS,
        check_timeout: int = DEFAULT_CHECK_TIMEOUT,
        region_tiers: list[str] | None = None,
        tier_delay: float = 0.15,
        variant_threshold: int = DEFAULT_VARIANT_THRESHOLD,
        taxonomy_file: str = DEFAULT_TAXONOMY_CACHE,
        ebird_key: str = "",
        rules_file: str = "",
        rules_export: str = DEFAULT_RULES_EXPORT,
        excel_export: str = DEFAULT_EXCEL_EXPORT,
        all_variants: bool = False,
        only_variants: set[str] | None = None,
        headless: bool = False,
        load_images: bool = False,
        force_dom: bool = False,
        diagnostic_mode: bool = True,
    ) -> None:

        self.reference_file = Path(reference_file)
        self.state_file = Path(state_file)
        self.url_export = Path(url_export)
        self.diagnostic_dir = Path(diagnostic_dir)

        self.target_images = target_images
        self.asset_size = asset_size
        self.thumb_size = thumb_size
        self.delay = delay
        self.page_timeout = page_timeout
        self.more_clicks = more_clicks
        self.check_timeout = check_timeout
        self.region_tiers = (
            list(DEFAULT_REGION_TIERS)
            if region_tiers is None
            else region_tiers
        )
        self.tier_delay = tier_delay
        self.variant_threshold = variant_threshold
        self.taxonomy_file = taxonomy_file
        self.ebird_key = ebird_key
        self.rules_file = rules_file
        self.rules_export = Path(rules_export)
        self.excel_export = Path(excel_export)
        self.all_variants = all_variants
        self.only_variants = only_variants

        # Set when a species actually fetched something, cleared when the CSV
        # and Excel exports are written. A resumed run that fetches nothing
        # should not rewrite them.
        self.pending_export = False

        # Species fetched since the state file was last written.
        self.unsaved = 0
        self.taxonomy: dict[str, dict[str, str]] = {}
        self.family_rules = dict(FAMILY_RULES)
        self.genus_rules = dict(GENUS_RULES)
        self.headless = headless
        self.load_images = load_images
        self.force_dom = force_dom
        self.diagnostic_mode = diagnostic_mode

        self.driver: webdriver.Chrome | None = None

        self.state: dict[str, Any] = self.load_state()

        self.diagnostic_dir.mkdir(parents=True, exist_ok=True)

        # Set once the browser is sitting on a Macaulay origin.
        self.session_ready = False

    # ========================================================
    # LOGGING
    # ========================================================

    @staticmethod
    def log(message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}", flush=True)

    @staticmethod
    def separator(char: str = "-", length: int = 72) -> None:
        print(char * length, flush=True)

    # ========================================================
    # STATE
    # ========================================================

    def load_state(self) -> dict[str, Any]:

        if not self.state_file.exists():
            return {
                "version": 3,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_updated": None,
                "species": {},
            }

        try:

            with self.state_file.open("r", encoding="utf-8") as f:
                state = json.load(f)

            if "species" not in state:
                state["species"] = {}

            return state

        except Exception as exc:

            self.log(f"WARNING: Could not read state file: {exc}")

            backup = self.state_file.with_suffix(".corrupt.json")

            try:
                self.state_file.rename(backup)
                self.log(f"Corrupt state backed up to: {backup}")
            except Exception:
                pass

            return {
                "version": 3,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_updated": None,
                "species": {},
            }

    @staticmethod
    def state_key(taxon: str, variant: str) -> str:

        return f"{taxon}|{variant}"

    def migrate_state(self) -> None:
        """
        Earlier runs keyed on the bare taxon code and had no variant
        filter, so those results are the unfiltered 'any' tier.
        Relabel rather than discard them.
        """

        species = self.state.get("species", {})

        moved = 0

        for key in list(species.keys()):

            if "|" in key:
                continue

            record = species.pop(key)

            record["variant"] = "any"

            for entry in record.get("assets", []):
                entry.setdefault("variant", "any")

            species[self.state_key(key, "any")] = record

            moved += 1

        if moved:

            self.log(
                f"Migrated {moved} existing species records to the "
                f"'any' variant."
            )

            self.save_state()

    def save_state(self) -> None:

        self.state["last_updated"] = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        temporary_file = self.state_file.with_suffix(
            self.state_file.suffix + ".tmp"
        )

        try:

            with temporary_file.open("w", encoding="utf-8") as f:

                # Compact, not pretty: nothing reads this by eye, and
                # indent=2 costs 15 MB and about two seconds every write.
                json.dump(
                    self.state,
                    f,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )

            os.replace(temporary_file, self.state_file)

        except Exception as exc:

            self.log(f"WARNING: Could not save state: {exc}")

    # ========================================================
    # DRIVER
    # ========================================================

    def start_driver(self) -> None:

        if self.driver is not None:
            return

        self.log("Starting Chrome...")

        options = webdriver.ChromeOptions()

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--log-level=3")

        # Nothing here needs pixels, so don't pay for them.
        if not self.load_images:

            options.add_experimental_option(
                "prefs",
                {
                    "profile.managed_default_content_settings.images": 2,
                },
            )

        options.page_load_strategy = "eager"

        self.driver = webdriver.Chrome(options=options)

        self.driver.set_page_load_timeout(self.page_timeout)
        self.driver.set_script_timeout(self.page_timeout)

        self.log("Chrome started.")

    def stop_driver(self) -> None:

        if self.driver is None:
            return

        try:
            self.driver.quit()
        except Exception:
            pass

        self.driver = None
        self.session_ready = False

    def ensure_session(self) -> None:
        """
        fetch() is same-origin, so Chrome has to be parked on a
        Macaulay page before the API calls will work. One page load
        for the entire run.
        """

        self.start_driver()

        if self.driver is None:
            return

        if self.session_ready:

            try:

                if MACAULAY_ORIGIN in self.driver.current_url:
                    return

            except WebDriverException:
                pass

        self.log("Establishing Macaulay session...")

        try:

            self.driver.get(
                f"{MACAULAY_SEARCH_URL}?{urlencode({'mediaType': 'photo'})}"
            )

            WebDriverWait(
                self.driver,
                min(self.page_timeout, 20),
            ).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Let any bot-check or cookie handshake settle.
            time.sleep(2.0)

            self.session_ready = True

            self.log("Session ready.")

        except (TimeoutException, WebDriverException) as exc:

            self.log(
                f"Session setup problem: {str(exc)[:150]}"
            )

        self.clear_human_check("initial session check")

    # ========================================================
    # HUMAN CHECK
    # ========================================================

    def probe_api(self) -> bool:
        """
        Cheapest possible API call. True means JSON came back, so the
        session is good.
        """

        result = self.api_get(
            self.api_url(PROBE_TAXON, count=1)
        )

        if result.get("error"):
            return False

        if self.looks_blocked(result):
            return False

        return bool(result.get("ok"))

    def clear_human_check(
        self,
        reason: str = "",
    ) -> bool:
        """
        Park Chrome on the catalog page so the check renders, then
        wait for the user to click through it. Polls the API until it
        starts returning JSON again.
        """

        if self.driver is None:
            return False

        if self.probe_api():
            return True

        if self.headless:

            self.log(
                "Blocked by a human check, but Chrome is headless "
                "so there is nothing to click. Re-run with "
                "--visible to clear it."
            )

            return False

        self.log("")
        self.separator("=")
        self.log("HUMAN CHECK REQUIRED")

        if reason:
            self.log(f"Trigger: {reason}")

        self.log(
            "Chrome is opening the Macaulay catalog. Click through "
            "whatever it asks for."
        )

        self.log(
            "The run continues by itself once the check clears. "
            "Ctrl+C to give up."
        )

        self.separator("=")

        try:

            self.driver.get(
                f"{MACAULAY_SEARCH_URL}?"
                + urlencode({"mediaType": "photo"})
            )

        except WebDriverException:
            pass

        deadline = time.time() + self.check_timeout

        announced = 0.0

        while time.time() < deadline:

            self.show_status(
                "WAITING FOR YOU",
                "Clear the human check in this window. "
                "The harvest resumes automatically.",
            )

            if self.probe_api():

                self.log("Check cleared. Carrying on.")

                self.show_status(
                    "Check cleared.",
                    "Resuming harvest...",
                )

                self.session_ready = True

                return True

            waited = time.time() - (deadline - self.check_timeout)

            if waited - announced >= 20:

                announced = waited

                self.log(
                    f"    Still waiting ({waited:.0f}s of "
                    f"{self.check_timeout}s)..."
                )

            time.sleep(3.0)

        self.log(
            "Human check not cleared within the timeout."
        )

        return False

    # ========================================================
    # ON-PAGE STATUS
    # ========================================================

    def show_status(
        self,
        message: str,
        detail: str = "",
    ) -> None:
        """
        In API mode the browser looks idle, because the work happens
        over XHR rather than through the UI. This paints the current
        species onto the page so the window shows what it is doing.
        """

        if self.driver is None:
            return

        if self.headless:
            return

        try:

            self.driver.execute_script(
                """
                let box = document.getElementById('harvest-status');

                if (!box) {
                    box = document.createElement('div');
                    box.id = 'harvest-status';
                    box.style.cssText =
                        'position:fixed;top:0;left:0;right:0;'
                        + 'z-index:2147483647;background:#101010;'
                        + 'color:#4ade80;font:15px/1.5 monospace;'
                        + 'padding:10px 14px;'
                        + 'border-bottom:2px solid #4ade80;'
                        + 'white-space:pre-wrap;';
                    document.body.appendChild(box);
                }

                box.textContent = arguments[0]
                    + (arguments[1] ? '\\n' + arguments[1] : '');
                """,
                message,
                detail,
            )

        except WebDriverException:
            pass

    # ========================================================
    # EXCEL
    # ========================================================

    def load_species(self) -> pd.DataFrame:

        self.log(f"Loading spreadsheet: {self.reference_file}")

        if not self.reference_file.exists():
            raise FileNotFoundError(
                f"Excel file not found:\n{self.reference_file}"
            )

        df = pd.read_excel(self.reference_file)

        taxon_columns = [
            "species_code",
            "species code",
            "taxonCode",
            "taxon code",
            "taxon_code",
            "Taxon Code",
            "Species Code",
            "speciesCode",
        ]

        name_columns = [
            "English name",
            "English Name",
            "english_name",
            "common_name",
            "Common Name",
        ]

        taxon_column = None

        for column in taxon_columns:
            if column in df.columns:
                taxon_column = column
                break

        if taxon_column is None:
            raise ValueError(
                "\nCould not find a taxon-code column.\n"
                "Expected one of:\n"
                + "\n".join(f"    {x}" for x in taxon_columns)
            )

        name_column = None

        for column in name_columns:
            if column in df.columns:
                name_column = column
                break

        result = pd.DataFrame()

        result["taxon"] = (
            df[taxon_column]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )

        if name_column:
            result["name"] = (
                df[name_column]
                .fillna("")
                .astype(str)
                .str.strip()
            )
        else:
            result["name"] = ""

        result = result[
            (result["taxon"] != "")
            & (result["taxon"] != "nan")
        ]

        result = result.drop_duplicates(
            subset=["taxon"],
            keep="first",
        )

        result = result.reset_index(drop=True)

        self.log(f"Found {len(result)} unique species.")

        return result


    # ========================================================
    # TAXONOMY AND RULES
    # ========================================================

    def load_taxonomy(self) -> None:
        """
        species_code -> (scientific name, genus, family).

        Uses a cached CSV if present, otherwise pulls the eBird
        taxonomy once with an API key. Without either, every variant
        gets asked for and the threshold does all the pruning.
        """

        self.taxonomy = {}

        path = Path(self.taxonomy_file)

        if not path.exists() and self.ebird_key:

            self.log("Downloading eBird taxonomy...")

            try:

                request = Request(
                    EBIRD_TAXONOMY_URL,
                    headers={"X-eBirdApiToken": self.ebird_key},
                )

                with urlopen(request, timeout=120) as response:
                    path.write_bytes(response.read())

                self.log(f"Taxonomy cached: {path}")

            except Exception as exc:

                self.log(
                    f"Taxonomy download failed: {str(exc)[:150]}"
                )

        if not path.exists():

            self.log(
                "No taxonomy available, so the family rules cannot "
                "be applied. Every variant will be asked for and "
                "pruned by the image-count threshold instead. "
                "Pass --ebird-key or --taxonomy to enable rules."
            )

            return

        try:

            frame = pd.read_csv(path, dtype=str).fillna("")

        except Exception as exc:

            self.log(f"Could not read taxonomy: {str(exc)[:150]}")

            return

        columns = {c.lower().replace("_", ""): c for c in frame.columns}

        def pick(*names: str) -> str:

            for name in names:
                if name in columns:
                    return columns[name]

            return ""

        code_column = pick("speciescode", "species code")
        sci_column = pick("sciname", "scientificname")
        family_column = pick("familysciname", "family", "familycomname")

        if not code_column:

            self.log(
                "Taxonomy file has no species-code column; "
                "rules disabled."
            )

            return

        for row in frame.itertuples(index=False):

            record = dict(zip(frame.columns, row))

            code = str(record.get(code_column, "")).strip().lower()

            if not code:
                continue

            sci = str(record.get(sci_column, "")).strip()

            family = str(record.get(family_column, "")).strip()

            # eBird writes family as "Icteridae (Troupials and Allies)".
            family = family.split("(")[0].strip()

            self.taxonomy[code] = {
                "sci_name": sci,
                "genus": sci.split(" ")[0] if sci else "",
                "family": family,
            }

        self.log(
            f"Taxonomy loaded for {len(self.taxonomy)} taxa."
        )

    def rule_for(self, taxon: str) -> dict[str, Any]:
        """
        Genus beats family beats the permissive default.
        """

        info = self.taxonomy.get(taxon)

        if not info:
            return dict(DEFAULT_RULE) | {"basis": "no taxonomy"}

        genus = info.get("genus", "")
        family = info.get("family", "")

        if genus in self.genus_rules:
            return dict(self.genus_rules[genus]) | {
                "basis": f"genus {genus}"
            }

        if family in self.family_rules:
            return dict(self.family_rules[family]) | {
                "basis": f"family {family}"
            }

        return dict(DEFAULT_RULE) | {
            "basis": f"default ({family or 'unknown family'})"
        }

    def variants_for(
        self,
        taxon: str,
    ) -> tuple[list[str], dict[str, Any]]:
        """
        The unfiltered tier is always collected. Male and female are
        added only where the sexes differ, and an age tier where
        immatures are worth separating.

        `adult` is added only where an age tier applies *and* the sexes
        look alike. The unfiltered tier is no substitute for it - `any`
        is whatever Macaulay's best-rated photographs show, which for a
        raptor is full of untagged juveniles - but the sex tiers are:
        both are requested with age=adult, so a bird in the male or
        female bank is already an adult. Asking for `adult` as well
        where the sexes differ would buy almost nothing for 234 extra
        requests, so it is skipped.

        What is left is the species where ages differ and the sexes do
        not: gulls, raptors, shorebirds, herons. Those have no sex bank
        to borrow an adult from, and they are the ones this exists for.
        """

        rule = self.rule_for(taxon)

        variants = ["any"]

        sexes_differ = bool(self.all_variants or rule.get("female"))

        if sexes_differ:
            variants.extend(["male", "female"])

        age = rule.get("age")

        if self.all_variants and not age:
            age = "juvenile"

        if age:
            if not sexes_differ:
                variants.append("adult")
            variants.append(age)

        if rule.get("flight"):
            variants.append("flight")

        # A run that only wants the new tier should not re-walk the ones
        # already in the state file. Filtering here rather than at the call
        # site keeps every caller honest, including the URL exports.
        if self.only_variants:
            variants = [v for v in variants if v in self.only_variants]

        return variants, rule

    def load_rule_overrides(self) -> None:
        """
        Optional CSV with columns: level,name,female,age
        e.g.  genus,Icterus,yes,immature
        """

        if not self.rules_file:
            return

        path = Path(self.rules_file)

        if not path.exists():

            self.log(f"Rules file not found: {path}")

            return

        try:
            frame = pd.read_csv(path, dtype=str).fillna("")
        except Exception as exc:
            self.log(f"Could not read rules: {str(exc)[:150]}")
            return

        applied = 0

        for row in frame.itertuples(index=False):

            record = {
                str(k).strip().lower(): str(v).strip()
                for k, v in zip(frame.columns, row)
            }

            level = record.get("level", "").lower()
            name = record.get("name", "")

            if not name:
                continue

            female = record.get("female", "").lower() in (
                "yes",
                "true",
                "1",
                "y",
            )

            age = record.get("age", "").lower()

            if age in ("", "none", "no", "-"):
                age = None

            rule = {"female": female, "age": age}

            if level.startswith("genus"):
                self.genus_rules[name] = rule
                applied += 1
            elif level.startswith("fam"):
                self.family_rules[name] = rule
                applied += 1

        self.log(f"Applied {applied} rule overrides from {path}.")

    def export_rules(self, species: pd.DataFrame) -> None:
        """
        Write out the decision made for every species, so the table
        can be checked and corrected.
        """

        rows = []

        for row in species.itertuples(index=False):

            taxon = str(row.taxon).strip().lower()

            variants, rule = self.variants_for(taxon)

            info = self.taxonomy.get(taxon, {})

            rows.append(
                {
                    "species_code": taxon,
                    "english_name": str(row.name).strip(),
                    "scientific_name": info.get("sci_name", ""),
                    "genus": info.get("genus", ""),
                    "family": info.get("family", ""),
                    "rule_basis": rule.get("basis", ""),
                    "female_wanted": (
                        "yes" if rule.get("female") else "no"
                    ),
                    "age_wanted": rule.get("age") or "",
                    "variants_asked": ",".join(variants),
                }
            )

        if not rows:
            return

        pd.DataFrame(rows).to_csv(
            self.rules_export,
            index=False,
            encoding="utf-8-sig",
        )

        self.log(f"Rule decisions written: {self.rules_export}")

    # ========================================================
    # URL CONSTRUCTION
    # ========================================================

    def catalog_url(
        self,
        taxon: str,
        region: str = "",
        variant: str = "any",
    ) -> str:

        parameters = {
            "taxonCode": taxon,
            "sort": "rating_rank_desc",
            "mediaType": "photo",
        }

        if region:
            parameters["regionCode"] = region

        parameters.update(
            VARIANT_FILTERS.get(variant, {})
        )

        return f"{MACAULAY_SEARCH_URL}?" + urlencode(parameters)

    def api_url(
        self,
        taxon: str,
        count: int | None = None,
        region: str = "",
        variant: str = "any",
    ) -> str:

        parameters = {
            "taxonCode": taxon,
            "mediaType": "photo",
            "sort": "rating_rank_desc",
            "count": (
                self.target_images
                if count is None
                else count
            ),
        }

        if region:
            parameters["regionCode"] = region

        parameters.update(
            VARIANT_FILTERS.get(variant, {})
        )

        return f"{MACAULAY_API_URL}?" + urlencode(parameters)

    @staticmethod
    def asset_url(asset_id: str, size: str) -> str:

        return (
            f"https://{IMAGE_CDN_HOST}"
            f"/api/v1/asset/{asset_id}/{size}"
        )

    @staticmethod
    def asset_page_url(asset_id: str) -> str:

        return f"https://macaulaylibrary.org/asset/{asset_id}"

    # ========================================================
    # PARSING
    # ========================================================

    @staticmethod
    def asset_ids_in(text: str) -> list[str]:

        found: list[str] = []
        seen: set[str] = set()

        for match in ASSET_PATTERN.finditer(text or ""):

            asset_id = match.group(1)

            if asset_id in seen:
                continue

            seen.add(asset_id)
            found.append(asset_id)

        return found

    @staticmethod
    def items_from_payload(payload: Any) -> list[dict[str, Any]]:
        """
        v2 has returned both a bare array and a nested
        results/content object, so accept either.
        """

        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]

        if isinstance(payload, dict):

            for key in ("content", "results", "data", "items"):

                value = payload.get(key)

                if isinstance(value, list):
                    return [
                        x for x in value if isinstance(x, dict)
                    ]

                if isinstance(value, dict):

                    inner = value.get("content")

                    if isinstance(inner, list):
                        return [
                            x for x in inner if isinstance(x, dict)
                        ]

        return []

    @staticmethod
    def first_value(
        item: dict[str, Any],
        keys: list[str],
    ) -> str:

        for key in keys:

            value = item.get(key)

            if value not in (None, "", []):
                return str(value)

        return ""

    def record_from_item(
        self,
        item: dict[str, Any],
    ) -> dict[str, str] | None:

        asset_id = self.first_value(
            item,
            [
                "assetId",
                "asset_id",
                "catalogId",
                "mlCatalogNumber",
                "id",
            ],
        )

        if not asset_id.isdigit():
            return None

        return {
            "asset_id": asset_id,
            "photographer": self.first_value(
                item,
                [
                    "userDisplayName",
                    "userName",
                    "recordist",
                    "contributor",
                ],
            ),
            "license": self.first_value(
                item,
                ["licenseType", "licenseId", "license"],
            ),
            "rating": self.first_value(
                item,
                ["rating", "avgRating", "ratingCount"],
            ),
            "location": self.first_value(
                item,
                ["locationLine1", "location", "localityName"],
            ),
            "region": self.first_value(
                item,
                ["subnational1Name", "countryName", "regionCode"],
            ),
            "date": self.first_value(
                item,
                ["obsDttm", "obsDate", "ebirdChecklistDate"],
            ),
            "checklist": self.first_value(
                item,
                ["ebirdChecklistId", "checklistId"],
            ),
        }

    # ========================================================
    # ROUTE A: IN-PAGE API CALL
    # ========================================================

    def api_get(
        self,
        url: str,
    ) -> dict[str, Any]:
        """
        Issue one in-page fetch. Returns the script result verbatim,
        or an error-shaped dict.
        """

        if self.driver is None:
            return {"ok": False, "status": 0, "error": "no driver"}

        try:

            result = self.driver.execute_async_script(
                API_FETCH_SCRIPT,
                url,
            )

        except Exception as exc:
            return {
                "ok": False,
                "status": 0,
                "error": f"script error: {str(exc)[:120]}",
            }

        if not isinstance(result, dict):
            return {
                "ok": False,
                "status": 0,
                "error": "empty script result",
            }

        return result

    @staticmethod
    def looks_blocked(result: dict[str, Any]) -> bool:
        """
        A human check comes back as an HTML page, usually with a 200,
        or as a 403/429. Either way it is not the JSON we asked for.
        """

        status = int(result.get("status", 0) or 0)

        if status in (401, 403, 429, 503):
            return True

        body = str(result.get("body", "")).lstrip()

        if not body:
            return False

        if body.startswith("<"):
            return True

        return False

    def fetch_one_region(
        self,
        taxon: str,
        region: str,
        variant: str = "any",
    ) -> tuple[list[dict[str, str]], str]:
        """
        One API call, one region, one variant. Returns
        (records, note).
        """

        url = self.api_url(
            taxon,
            region=region,
            variant=variant,
        )

        result = self.api_get(url)

        if result.get("error"):
            return [], str(result["error"])

        body = str(result.get("body", ""))

        status = result.get("status", 0)

        if self.looks_blocked(result):
            return [], "blocked"

        if not result.get("ok"):
            return [], f"HTTP {status}"

        if body.lstrip().startswith("<"):
            return [], "blocked"

        records: list[dict[str, str]] = []

        seen: set[str] = set()

        try:

            payload = json.loads(body)

            for item in self.items_from_payload(payload):

                record = self.record_from_item(item)

                if record is None:
                    continue

                if record["asset_id"] in seen:
                    continue

                seen.add(record["asset_id"])
                records.append(record)

        except json.JSONDecodeError:
            pass

        # Shape changed but the IDs are still in there somewhere.
        if not records:

            for asset_id in self.asset_ids_in(body):

                records.append(
                    {
                        "asset_id": asset_id,
                        "photographer": "",
                        "license": "",
                        "rating": "",
                        "location": "",
                        "region": "",
                        "date": "",
                        "checklist": "",
                    }
                )

            if records:
                return records, "regex"

        if not records:

            self.save_api_diagnostic(taxon, body)

            return [], "empty"

        return records, "api"

    def fetch_via_api(
        self,
        taxon: str,
        variant: str = "any",
    ) -> tuple[list[dict[str, str]], str]:
        """
        Walk the region tiers in order, taking the best-rated photos
        from Chiapas first, then the rest of Mexico, then worldwide,
        stopping as soon as the quota is filled. Each record is
        tagged with the tier it came from.
        """

        self.ensure_session()

        if self.driver is None:
            return [], "no driver"

        collected: list[dict[str, str]] = []

        seen: set[str] = set()

        tiers_used: list[str] = []

        last_note = "empty"

        for region in self.region_tiers:

            if len(collected) >= self.target_images:
                break

            label = region or "world"

            self.show_status(
                f"{taxon}  [{variant}]",
                f"searching {label}... "
                f"({len(collected)}/{self.target_images})",
            )

            records, note = self.fetch_one_region(
                taxon,
                region,
                variant=variant,
            )

            last_note = note

            if note == "blocked":
                return [], "blocked"

            added = 0

            for record in records:

                if record["asset_id"] in seen:
                    continue

                seen.add(record["asset_id"])

                record["region_tier"] = label
                record["variant"] = variant

                collected.append(record)

                added += 1

                if len(collected) >= self.target_images:
                    break

            if added:
                tiers_used.append(f"{label}:{added}")

            if self.tier_delay > 0:
                time.sleep(self.tier_delay)

        if not collected:
            return [], last_note

        return collected, "api " + "+".join(tiers_used)

    def save_api_diagnostic(
        self,
        taxon: str,
        body: str,
    ) -> None:

        if not self.diagnostic_mode:
            return

        try:

            path = (
                self.diagnostic_dir
                / f"{taxon}_api_body.txt"
            )

            path.write_text(
                body[:200000],
                encoding="utf-8",
                errors="ignore",
            )

            self.log(f"    API body saved: {path}")

        except Exception:
            pass

    # ========================================================
    # ROUTE B: RENDERED GRID
    # ========================================================

    def fetch_via_dom(
        self,
        taxon: str,
        variant: str = "any",
    ) -> list[dict[str, str]]:

        self.start_driver()

        if self.driver is None:
            return []

        # The grid is slow, so the fallback only uses the widest
        # tier rather than walking all of them.
        region = self.region_tiers[-1] if self.region_tiers else ""

        url = self.catalog_url(
            taxon,
            region=region,
            variant=variant,
        )

        try:
            self.driver.get(url)
        except TimeoutException:
            pass
        except WebDriverException as exc:
            self.log(f"    Chrome error: {str(exc)[:150]}")
            return []

        assets: dict[str, None] = {}

        deadline = time.time() + min(self.page_timeout, 20)

        while time.time() < deadline and not assets:

            for asset_id in self.harvest_dom_assets():
                assets.setdefault(asset_id, None)

            if not assets:
                time.sleep(1.0)

        stalled = 0

        for _ in range(self.more_clicks):

            if len(assets) >= self.target_images:
                break

            before = len(assets)

            self.scroll_page()
            clicked = self.click_more_results()

            wait_until = time.time() + 8

            while time.time() < wait_until:

                for asset_id in self.harvest_dom_assets():
                    assets.setdefault(asset_id, None)

                if len(assets) > before:
                    break

                time.sleep(0.5)

            if len(assets) <= before:

                stalled += 1

                if stalled >= 2:
                    break

            else:
                stalled = 0

            if not clicked and stalled:
                break

        return [
            {
                "asset_id": asset_id,
                "photographer": "",
                "license": "",
                "rating": "",
                "location": "",
                "region": "",
                "date": "",
                "checklist": "",
                "region_tier": (region or "world"),
                "variant": variant,
            }
            for asset_id in list(assets.keys())[:self.target_images]
        ]

    def harvest_dom_assets(self) -> list[str]:

        if self.driver is None:
            return []

        candidates: list[str] = []

        try:

            candidates = self.driver.execute_script(
                HARVEST_SCRIPT
            ) or []

        except WebDriverException:
            pass

        try:
            candidates.append(self.driver.page_source)
        except WebDriverException:
            pass

        found: list[str] = []

        for value in candidates:
            found.extend(self.asset_ids_in(str(value)))

        return found

    def scroll_page(self) -> None:

        if self.driver is None:
            return

        try:

            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )

            time.sleep(0.5)

        except WebDriverException:
            pass

    def click_more_results(self) -> bool:

        if self.driver is None:
            return False

        lowercase = (
            "translate(., "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')"
        )

        selectors = [
            (By.XPATH, f"//button[contains({lowercase}, 'more results')]"),
            (By.XPATH, f"//button[contains({lowercase}, 'show more')]"),
            (By.XPATH, f"//button[contains({lowercase}, 'load more')]"),
            (By.CSS_SELECTOR, "button[class*='More'], button[class*='more']"),
        ]

        for by, selector in selectors:

            try:
                elements = self.driver.find_elements(by, selector)
            except WebDriverException:
                continue

            for element in reversed(elements):

                try:

                    if not (
                        element.is_displayed()
                        and element.is_enabled()
                    ):
                        continue

                    self.driver.execute_script(
                        "arguments[0].click();",
                        element,
                    )

                    return True

                except (
                    StaleElementReferenceException,
                    WebDriverException,
                ):
                    continue

        return False

    # ========================================================
    # EXPORT
    # ========================================================

    def export_urls(self) -> None:

        rows = []

        for taxon, record in self.state["species"].items():

            name = record.get("name", "")

            if not record.get("kept", True):
                continue

            for rank, entry in enumerate(
                record.get("assets", []),
                start=1,
            ):

                asset_id = entry.get("asset_id", "")

                if not asset_id:
                    continue

                rows.append(
                    {
                        "taxon": record.get("taxon", taxon),
                        "english_name": name,
                        "variant": record.get("variant", "any"),
                        "rank": rank,
                        "asset_id": asset_id,
                        "image_url": self.asset_url(
                            asset_id,
                            self.asset_size,
                        ),
                        "thumbnail_url": self.asset_url(
                            asset_id,
                            self.thumb_size,
                        ),
                        "asset_page": self.asset_page_url(
                            asset_id
                        ),
                        "region_tier": entry.get(
                            "region_tier",
                            "",
                        ),
                        "photographer": entry.get(
                            "photographer",
                            "",
                        ),
                        "license": entry.get("license", ""),
                        "rating": entry.get("rating", ""),
                        "location": entry.get("location", ""),
                        "region": entry.get("region", ""),
                        "date": entry.get("date", ""),
                        "checklist": entry.get("checklist", ""),
                    }
                )

        if not rows:
            return

        pd.DataFrame(rows).to_csv(
            self.url_export,
            index=False,
            encoding="utf-8-sig",
        )

    # ========================================================
    # SUMMARY
    # ========================================================


    def export_excel(self) -> None:
        """
        The reference spreadsheet, expanded to one row per species
        per variant that was actually kept.
        """

        rows = []

        for key, record in self.state["species"].items():

            taxon = record.get("taxon", key.split("|")[0])

            assets = record.get("assets", [])

            info = self.taxonomy.get(taxon, {})

            top = assets[0] if assets else {}

            rows.append(
                {
                    "species_code": taxon,
                    "english_name": record.get("name", ""),
                    "scientific_name": info.get("sci_name", ""),
                    "genus": info.get("genus", ""),
                    "family": info.get("family", ""),
                    "variant": record.get("variant", "any"),
                    "rule_basis": record.get("rule_basis", ""),
                    "images_found": len(assets),
                    "kept": (
                        "yes" if record.get("kept", True) else "no"
                    ),
                    "top_image_url": (
                        self.asset_url(
                            top.get("asset_id", ""),
                            self.asset_size,
                        )
                        if top.get("asset_id")
                        else ""
                    ),
                    "top_asset_id": top.get("asset_id", ""),
                    "top_photographer": top.get("photographer", ""),
                    "top_region_tier": top.get("region_tier", ""),
                    "catalog_url": record.get("catalog_url", ""),
                }
            )

        if not rows:
            return

        frame = pd.DataFrame(rows)

        variant_order = {
            "any": 0,
            "male": 1,
            "female": 2,
            "immature": 3,
            "juvenile": 4,
        }

        frame["_order"] = frame["variant"].map(
            lambda v: variant_order.get(v, 9)
        )

        frame = frame.sort_values(
            ["english_name", "_order"]
        ).drop(columns=["_order"])

        try:

            frame.to_excel(self.excel_export, index=False)

        except Exception as exc:

            self.log(
                f"Excel export failed ({str(exc)[:120]}); "
                f"writing CSV instead."
            )

            frame.to_csv(
                self.excel_export.with_suffix(".csv"),
                index=False,
                encoding="utf-8-sig",
            )

    def print_summary(self) -> None:

        species = self.state.get("species", {})

        complete = 0
        partial = 0
        empty = 0
        total_assets = 0

        for record in species.values():

            count = len(record.get("assets", []))

            total_assets += count

            if count == 0:
                empty += 1
            elif count >= self.target_images:
                complete += 1
            else:
                partial += 1

        by_variant: dict[str, int] = {}

        for key, record in species.items():

            if not record.get("kept", True):
                continue

            variant = record.get("variant", "any")

            by_variant[variant] = by_variant.get(variant, 0) + len(
                record.get("assets", [])
            )

        print()
        print("=" * 60)
        print("HARVEST SUMMARY")
        print("=" * 60)
        print(f"Species recorded:  {len(species)}")
        print(f"Full quota:        {complete}")
        print(f"Partial:           {partial}")
        print(f"No assets:         {empty}")
        print(f"URLs collected:    {total_assets}")
        for variant, count in sorted(by_variant.items()):
            print(f"  {variant:<10} {count} URLs")

        print(f"CSV:               {self.url_export.resolve()}")
        print(f"Excel:             {self.excel_export.resolve()}")
        print("=" * 60)

    # ========================================================
    # MAIN RUN
    # ========================================================

    def run(
        self,
        limit: int | None = None,
        start_at: int = 0,
    ) -> None:

        species = self.load_species()

        self.load_taxonomy()
        self.load_rule_overrides()
        self.migrate_state()

        if start_at > 0:
            species = species.iloc[start_at:]

        if limit is not None:
            species = species.iloc[:limit]

        total_species = len(species)

        print()
        print("=" * 60)
        print("MACAULAY LIBRARY URL HARVESTER")
        print("=" * 60)
        print(f"Species:          {total_species}")
        print(f"URLs/species:     {self.target_images}")
        print(f"Image size:       {self.asset_size}")
        print(
            f"Route:            "
            f"{'DOM only' if self.force_dom else 'API, DOM fallback'}"
        )
        print(
            f"Chrome:           "
            f"{'headless' if self.headless else 'visible'}"
        )
        print(
            "Region order:     "
            + " then ".join(
                region or "worldwide"
                for region in self.region_tiers
            )
        )
        print(f"State:            {self.state_file.resolve()}")
        print(f"CSV:              {self.url_export.resolve()}")
        print("=" * 60)
        print()

        self.export_rules(species)

        started = time.time()

        processed = 0

        try:

            for position, row in enumerate(
                species.itertuples(index=False),
                start=1,
            ):

                taxon = str(row.taxon).strip().lower()
                name = str(row.name).strip()

                summary: list[str] = []

                # Everything below - saving the 72 MB state file, the CSV and
                # Excel exports, the courtesy delay - exists to record work.
                # A species whose variants are all already in the state file
                # did none, so none of it should run for it.
                fetched_any = False

                wanted, rule = self.variants_for(taxon)

                # --only-variants rules most species out. Skipping here costs
                # nothing; falling through would still pay the status line, the
                # export bookkeeping and the courtesy delay for every one of a
                # thousand birds that has no work to do.
                if not wanted:
                    continue

                for variant in wanted:

                    key = self.state_key(taxon, variant)

                    existing = self.state["species"].get(key, {})

                    if existing.get("last_updated"):

                        summary.append(
                            f"{variant}:"
                            f"{len(existing.get('assets', []))}*"
                        )

                        continue

                    records: list[dict[str, str]] = []
                    note = "dom"

                    self.show_status(
                        f"[{position}/{total_species}]  {taxon}"
                        + (f"  ({name})" if name else ""),
                        f"variant: {variant}",
                    )

                    if not self.force_dom:

                        records, note = self.fetch_via_api(
                            taxon,
                            variant=variant,
                        )

                        if not records and note == "blocked":

                            if self.clear_human_check(
                                f"blocked at {taxon} ({variant})"
                            ):

                                records, note = self.fetch_via_api(
                                    taxon,
                                    variant=variant,
                                )

                        if not records and note == "blocked":

                            self.log(
                                "    Still blocked; falling back "
                                "to the grid."
                            )

                            records = self.fetch_via_dom(
                                taxon,
                                variant=variant,
                            )

                            note = "dom"

                    else:

                        records = self.fetch_via_dom(
                            taxon,
                            variant=variant,
                        )

                        note = "dom"

                    # An age tag that nobody uses for this group is
                    # worth one retry with the other tag before it is
                    # written off.
                    if (
                        variant in ("juvenile", "immature")
                        and len(records) < self.variant_threshold
                        and not self.force_dom
                    ):

                        other = (
                            "immature"
                            if variant == "juvenile"
                            else "juvenile"
                        )

                        alternative, _ = self.fetch_via_api(
                            taxon,
                            variant=other,
                        )

                        if len(alternative) > len(records):

                            records = alternative
                            variant = other
                            key = self.state_key(taxon, variant)
                            note = f"{note} (as {other})"

                    records = records[:self.target_images]

                    kept = (
                        variant == "any"
                        or len(records) >= self.variant_threshold
                    )

                    self.state["species"][key] = {
                        "taxon": taxon,
                        "name": name,
                        "variant": variant,
                        "rule_basis": rule.get("basis", ""),
                        "catalog_url": self.catalog_url(
                            taxon,
                            variant=variant,
                        ),
                        "assets": records,
                        "kept": kept,
                        "source": note,
                        "last_updated": time.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    }

                    fetched_any = True

                    summary.append(
                        f"{variant}:{len(records)}"
                        + ("" if kept else "(thin)")
                    )

                # Writing the whole state file per species costs ~72 MB of IO
                # each time. Over a resumed run that is tens of gigabytes spent
                # recording that nothing changed.
                if fetched_any:
                    self.unsaved += 1
                    self.pending_export = True
                    if self.unsaved >= SAVE_EVERY:
                        self.save_state()
                        self.unsaved = 0

                processed += 1

                elapsed = time.time() - started

                rate = elapsed / max(processed, 1)

                remaining = (total_species - position) * rate

                self.log(
                    f"[{position}/{total_species}] {taxon} "
                    f"({name}): {'  '.join(summary)}. "
                    f"~{remaining / 60:.0f} min left."
                )

                self.show_status(
                    f"[{position}/{total_species}]  {taxon}"
                    + (f"  ({name})" if name else ""),
                    f"{'   '.join(summary)}"
                    f"   |   ~{remaining / 60:.0f} min remaining",
                )

                if (
                    self.pending_export
                    and processed % EXPORT_EVERY == 0
                ):
                    self.export_urls()
                    self.export_excel()
                    self.pending_export = False

                # The delay is there to be polite to Macaulay. A skipped
                # species never touched it, so there is nothing to be polite
                # about - and 0.3s across a thousand skips is five minutes.
                if fetched_any and self.delay > 0:
                    time.sleep(self.delay)

        finally:

            self.stop_driver()
            self.export_urls()
            self.export_excel()
            self.save_state()
            self.print_summary()


# ============================================================
# COMMAND LINE
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Collect Macaulay Library image URLs and credit "
            "metadata without downloading the images."
        )
    )

    parser.add_argument("--reference", default=DEFAULT_REFERENCE_FILE)
    parser.add_argument("--state", default=DEFAULT_STATE_FILE)
    parser.add_argument("--url-export", default=DEFAULT_URL_EXPORT)
    parser.add_argument(
        "--diagnostics",
        default=DEFAULT_DIAGNOSTIC_DIRECTORY,
    )

    parser.add_argument(
        "--images",
        type=int,
        default=DEFAULT_IMAGES_PER_SPECIES,
        help="URLs to collect per species.",
    )

    parser.add_argument(
        "--size",
        default=DEFAULT_ASSET_SIZE,
        help="Size token used to build the image URL.",
    )

    parser.add_argument(
        "--thumb-size",
        default=DEFAULT_THUMB_SIZE,
        help="Size token used for the thumbnail URL column.",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Pause between species.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_PAGE_TIMEOUT,
    )

    parser.add_argument(
        "--more-clicks",
        type=int,
        default=DEFAULT_MORE_CLICKS,
        help="Pagination rounds, DOM fallback only.",
    )

    parser.add_argument(
        "--ebird-key",
        default=(
            os.environ.get("EBIRD_API_KEY", "")
            or EBIRD_API_KEY
        ),
        help=(
            "eBird API token, used once to download the taxonomy "
            "for the family join. Falls back to the EBIRD_API_KEY "
            "environment variable."
        ),
    )

    parser.add_argument(
        "--taxonomy",
        default=DEFAULT_TAXONOMY_CACHE,
        help="Cached eBird taxonomy CSV.",
    )

    parser.add_argument(
        "--rules",
        default="",
        help=(
            "Optional CSV of rule overrides with columns "
            "level,name,female,age (level is family or genus)."
        ),
    )

    parser.add_argument(
        "--rules-export",
        default=DEFAULT_RULES_EXPORT,
        help="Where to write the decision made for each species.",
    )

    parser.add_argument(
        "--excel-export",
        default=DEFAULT_EXCEL_EXPORT,
        help="Expanded reference workbook, one row per variant.",
    )

    parser.add_argument(
        "--variant-threshold",
        type=int,
        default=DEFAULT_VARIANT_THRESHOLD,
        help=(
            "Minimum tagged photos for a variant to be kept. "
            "Thin variants are recorded but excluded from the "
            "exports."
        ),
    )

    parser.add_argument(
        "--all-variants",
        action="store_true",
        help=(
            "Ignore the family rules and ask for every variant on "
            "every species."
        ),
    )

    parser.add_argument(
        "--regions",
        default=",".join(
            region or "world"
            for region in DEFAULT_REGION_TIERS
        ),
        help=(
            "Comma-separated eBird region codes, searched in "
            "order until the quota fills. Use 'world' for the "
            "unfiltered tier. Example: MX-CHP,MX,world"
        ),
    )

    parser.add_argument(
        "--only-variants",
        default="",
        help=(
            "Comma-separated variant names to run, skipping every "
            "other tier. Use it to add a newly introduced tier "
            "without re-walking the ones already harvested, e.g. "
            "--only-variants flight."
        ),
    )

    parser.add_argument(
        "--check-timeout",
        type=int,
        default=DEFAULT_CHECK_TIMEOUT,
        help=(
            "Seconds to wait for you to clear a human check "
            "before giving up."
        ),
    )

    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-at", type=int, default=0)

    parser.add_argument(
        "--headless",
        action="store_true",
        help=(
            "Hide Chrome. Only safe once you know the session is "
            "clear, since a human check cannot be clicked."
        ),
    )

    parser.add_argument(
        "--load-images",
        action="store_true",
        help=(
            "Let Chrome actually render the photos. Off by "
            "default, since only the IDs are wanted."
        ),
    )

    parser.add_argument(
        "--dom",
        action="store_true",
        help="Skip the API route and scrape the grid.",
    )

    parser.add_argument(
        "--no-diagnostics",
        action="store_true",
    )

    args = parser.parse_args()

    only_variants = {
        part.strip()
        for part in args.only_variants.split(",")
        if part.strip()
    } or None

    if only_variants:
        unknown = sorted(only_variants - set(VARIANT_FILTERS))
        if unknown:
            raise SystemExit(
                f"--only-variants: no such variant: {', '.join(unknown)}\n"
                f"Known variants: {', '.join(VARIANT_FILTERS)}"
            )
        # Which variants a species gets comes from the family rules, and those
        # need the taxonomy. Without it every species falls back to
        # DEFAULT_RULE, which asks for neither `flight` nor `immature` - so a
        # filtered run would walk a thousand birds and fetch nothing at all,
        # silently. Refuse instead.
        from_rules = only_variants - set(DEFAULT_VARIANTS)
        if from_rules and not Path(args.taxonomy).exists():
            raise SystemExit(
                f"--only-variants {', '.join(sorted(from_rules))} needs the "
                "family rules, which need the eBird taxonomy.\n"
                f"No taxonomy at {args.taxonomy} - pass --taxonomy or "
                "--ebird-key.\n"
                "Without it every species falls back to the permissive default "
                "rule, which never asks for these, and the run would fetch "
                "nothing."
            )

    if args.images < 1:
        raise ValueError("--images must be at least 1.")

    harvester = MacaulayUrlHarvester(

        reference_file=args.reference,

        state_file=args.state,

        url_export=args.url_export,

        diagnostic_dir=args.diagnostics,

        target_images=args.images,

        asset_size=args.size,

        thumb_size=args.thumb_size,

        delay=args.delay,

        page_timeout=args.timeout,

        more_clicks=args.more_clicks,

        check_timeout=args.check_timeout,

        variant_threshold=args.variant_threshold,

        taxonomy_file=args.taxonomy,

        ebird_key=args.ebird_key,

        rules_file=args.rules,

        rules_export=args.rules_export,

        excel_export=args.excel_export,

        all_variants=args.all_variants,

        only_variants=only_variants,

        region_tiers=[
            "" if part.strip().lower() in ("world", "global", "")
            else part.strip()
            for part in args.regions.split(",")
        ],

        headless=args.headless,

        load_images=args.load_images,

        force_dom=args.dom,

        diagnostic_mode=not args.no_diagnostics,
    )

    try:

        harvester.run(
            limit=args.limit,
            start_at=args.start_at,
        )

    except KeyboardInterrupt:

        print()
        print("Interrupted. Progress saved.")

        harvester.stop_driver()
        harvester.export_urls()
        harvester.save_state()

        sys.exit(130)

    except Exception as exc:

        print()
        print("FATAL ERROR:")
        print(str(exc))

        harvester.stop_driver()
        harvester.export_urls()
        harvester.save_state()

        raise


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()