# Chiapas confusion quiz

A bird ID quiz that puts species head to head. You choose the cast, the quiz
shows one of them, and after you answer it tells you what actually separates
them.

## The idea

Pick the birds you confuse. That is the whole curriculum — there is no computed
difficulty and no ordering, because a birder already knows which pairs hurt.
What the quiz owes you is not a ranking but an **explanation**: for every pair
of species on the board, a note saying which marks to use.

Those notes live in `src/lib/data/quiz/pair_notes.json`, keyed by the two eBird
codes sorted and joined with `|`. They are attached to the *pair*, not to a
species, because what separates Alder from Willow is not a fact about Alder.

## Running it yourself

Everything below is run from the site folder:

    cd "C:/Users/52967/Cardellina/bird-quiz"

**To play the quiz**, start the dev server and leave it running:

    npm run dev

It prints the address it chose - usually <http://localhost:5173>. The quiz is at
the root and the editor at `/edit`. Use `localhost`, not `127.0.0.1`: Vite sometimes binds IPv6 only.
Stop it with Ctrl-C.

**To run a pipeline script**, use anaconda's Python, not the `python` on PATH -
that one is a bare 3.14 without `requests`, `openpyxl` or `Pillow`:

    ~/anaconda3/python.exe quiz/pipeline/fetch_photos.py --sync

**To wait for Macaulay and harvest whenever it lets us in:**

    bash quiz/pipeline/watch_macaulay.sh

That one is worth running in your own terminal rather than through Claude, so
it survives the session.

**To check the code still compiles:**

    npx svelte-check

**To build the real site** (what gets published):

    npm run build

Inside Claude Code you can run any of these by typing `!` first, e.g.
`! npm run dev`, which runs it in the session so the output lands in the
conversation.

## Pipeline

Two scripts, and neither is needed to play — the outputs are committed.

| Script | Output |
|---|---|
| `fetch_chiapas.py` | regional status labels + Spanish names (needs an eBird API key) |
| `export_web.py` | `src/lib/data/quiz/index.json` — codes, names, family, genus |
| `fetch_photos.py` | `src/lib/data/quiz/photos.json` — the photograph bank |

```
~/anaconda3/python.exe quiz/pipeline/export_web.py
~/anaconda3/python.exe quiz/pipeline/fetch_photos.py        # all species, slow
~/anaconda3/python.exe quiz/pipeline/fetch_photos.py wewpew # or just a few
~/anaconda3/python.exe quiz/pipeline/fetch_photos.py --sync # publish what is cached
```

Without `fetch_chiapas.py` there are no Spanish names and no regional labels;
everything else still works.

**The species pool is never filtered by region.** Every species in the reference
sheet stays in, and eBird's regional lists are joined on as a label
(`chiapas` / `neighbouring` / `yucatan` / `guatemala` / `belize` / `wider`).
Vagrancy is real and concentrated in exactly the migratory groups this quiz
exists for — a bird you have trained yourself never to consider is a bird you
will call wrong when it finally turns up.

### Photographs

From the Macaulay Library, **nothing below 2.5 stars**, 50 per species. Two
requests each: Mexican checklists first (30 of the 50 where they exist), then
anywhere for the rest — a Western Wood-Pewee does not change appearance at the
border, but the subspecies on your patch should be over-represented.

The 50 are **sampled from a pool of 500**, not taken from the top. The top 50
are fifty portraits of a perched adult in golden hour, which is the one bird
nobody has trouble identifying.

Two API quirks worth knowing before you change anything:

- `qua`, the quality filter, is **silently ignored** — every value returns
  identical results — so the rating floor is applied in the script.
- `sort=rating_rank_desc` is a *composite* rank, not a pure rating sort, so
  ratings do not descend monotonically. You cannot stop paging on a low one.

Identifiable subspecies groups (`issf` — Crane Hawk Blackish/Banded/Gray) are
kept, because eBird reports them *as* the species and three plumages teach more
than 454 of the nominate. Hybrids and `sp.` records are not.

A full harvest takes the best part of an hour, so it publishes `photos.json` at
every checkpoint rather than only at the end. **A species with no photograph
cannot be asked about**, however complete the rest of its data, so an unwritten
bank looks exactly like missing species in the app.

To jump the queue for a group while a long harvest is still running, send the
targeted run to its own cache:

```
QUIZ_PHOTO_CACHE=photos_inat_empids.json   ~/anaconda3/python.exe quiz/pipeline/fetch_photos.py leafly wilfly whtfly1
```

Both processes then write different files, and the bank is every
`data/raw/photos_inat*.json` merged. Sharing one cache would lose whichever run
checkpointed first, because each rewrites the file whole.

## How the quiz plays

Choose two or more species on the setup screen. Those species *are* the cast —
nothing else is mixed in, and the difficulty is whatever you made it.

For each species you can also choose **which plumages** of it are in play:
all together by default, or only males, only females, only juveniles. The
choice is per species, which is the point — it is what lets you drill male
Acadian against female Least rather than being stuck with one global filter.

Answer, and the quiz shows the pair note for every rival on the board plus the
plumage the photograph was.

There is no score. Getting a percentage was never the reason to open this.

### Recommended comparison species

Choose Acadian Flycatcher and the setup screen offers the rest of *Empidonax*,
then the rest of the family. Taxonomy is a good enough proxy for "looks alike"
that it needs no data of its own: the birds you confuse are overwhelmingly the
ones sharing a genus, and after that a family.

## Data sources

- **eBird** — species codes, taxonomic order, regional list, Spanish names.
- **Macaulay Library** — photographs. Addressed by eBird species code, which is
  this project's own primary key, so there is no name to translate and no way to
  fetch the wrong bird.
- **`src/lib/data/species.ts`** — the bird library's hand-tagged habitat zones,
  which exist in no public dataset.
- **Field guides, for the pair notes** — see below.

## Where the pair notes come from

The notes are written by hand from ID literature: Howell & Webb for Mexico,
Cin-Ty Lee & Birch for the flycatchers, van Dort's eBird Central America
articles for individual groups.

**Facts are extracted; the prose is written fresh.** Field marks are facts and
free to use, but the authors' wording is theirs, so nothing is transcribed and
no note names its source. Howell & Webb's own `SS:` (similar species) field is
the most useful thing in the book for this, because it says which pairs a real
observer confuses — a genus of 24 species has 276 pairs but only a couple of
dozen `SS:` links, and those are the ones worth writing.

Each line of a note is `label: body`, rendered as a definition list:

```
primary projection: Alder long, Willow medium
lower mandible: Willow orange, Alder dark
Voice — Alder: a flat free-BEER. Willow: a sneezed fitz-bew
```

Two details the renderer imposes. The label must be **under 34 characters** or
the line renders as a plain sentence instead — which is itself useful, for
"this pair is genuinely close, take every mark". And voice and behaviour rows
use an **em dash**, so never put one inside a trait row: the renderer cuts at
whichever of `:` and `—` comes first.

`quiz/pipeline/build_pair_notes.py` seeds notes for the flycatchers from
`data/empid_traits.csv`. Everything else is written directly.

## Sex and age variants

Some birds need more than one bank of photographs, and which ones is **two
questions, not one**:

- **sexes differ** - ducks, hummingbirds, orioles, buntings, becards
- **ages differ** - raptors, gulls, herons, boobies, vultures

Those groups barely overlap. A juvenile Cooper's Hawk is a genuinely different
bird to identify while male and female are the same bird at different sizes; a
drake Blue-winged Teal and the hen are unrelated to look at while the ages are
much of a muchness. One combined "dimorphic" flag gets both wrong, so there are
two.

`data/plumage_classes.csv` holds the answer: family defaults with species
overrides. Anything unlisted gets one bank - adults, sexes together. Check what
it decided:

    ~/anaconda3/python.exe quiz/pipeline/plumage.py
    ~/anaconda3/python.exe quiz/pipeline/plumage.py --list Accipitridae

As it stands that is **596 species needing nothing and 477 needing something** -
176 for sex, 161 for age, 140 for both.

What the rules *want* and what the bank actually *holds* are different
questions, and the second is the one that decides what the quiz can offer. Add
`--bank` to read the packed photos.json the same way the app does:

    ~/anaconda3/python.exe quiz/pipeline/plumage.py --bank
    ~/anaconda3/python.exe quiz/pipeline/plumage.py --bank --list Trogonidae

That also lists the species the rules asked variants for and the harvest found
none of, which is the list a re-harvest would shorten. Currently **606 species
of 1,073 have a sex or age bank**: 404 male, 378 female, 281 immature, 194
juvenile.

Which variants a species ends up with follows Macaulay's taggers, not the
rules. Raptors come back as `immature` far more than `juvenile`, so the black
hawks offer *All | immature* and nothing else. Thirty-two species the rules
wanted variants for have none at all — meadowlarks, oropendolas and
wood-partridges mostly, where nobody bothers tagging a sex because the sexes
look alike.

There is no free dataset for this, which is worth knowing before you go looking.
The published comparative work on plumage dichromatism covers passerines, which
is the half that matters least here - the hard cases are raptors, gulls and
ducks. Birds of the World has it in prose, behind a paywall, with no bulk
export. So the file is judgement, and it is meant to be corrected when the quiz
shows you something daft.

A third axis is deliberately not modelled: **breeding versus nonbreeding**,
which is the dominant one for shorebirds. Macaulay has no season filter, so it
would have to be inferred from the observation month.

In the quiz, variants are **mixed into the normal deck** unless you filter them,
because being handed a juvenile and still having to name the species is the
actual skill. The plumage is revealed *after* you answer - saying "juvenile" up
front rules out most of the board by itself.

### `any` is not `adult`

This is the trap. `any` is the **unfiltered** search: the best-rated
photographs of the species, whatever they show. For a raptor that means plenty
of untagged juveniles, because juvenile raptors are abundant and photogenic. So
an "All" deck for Crane Hawk is not 77% adults and 23% immatures - it is 23%
*tagged* immature plus an unknown slice of the `any` bank that is also young.

Which is why `adult` is a harvested variant of its own, collected wherever an
age tier is. Without it the quiz can drill young birds but cannot exclude them,
and there is no way to ask for an adult at all: leaving the filter off gets you
everything, and no combination of the other pills is the complement.

### A sexed bird is an adult

Most of that came for free. Macaulay's male and female searches are both sent
with `age=adult`, so **every photograph in a sex bank is an adult by
construction** - 11,174 of them across 407 species. Asking for `adult`
therefore accepts `male` and `female` too (`satisfiesVariant` in pins.ts), and
those species get an adult deck without harvesting anything.

The implication runs one way only: asking for `male` must not return an
unsexed adult.

What it cannot cover is the species where **ages differ but sexes look alike**,
because those have no sex bank to borrow from. That is 199 species and they are
exactly the hard ones - 34 gulls, 34 raptors, 32 shorebirds, 21 thrushes, 16
herons. `plumage.py --bank` lists them.

## Importing a URL harvest

`quiz/pipeline/import_ml_csv.py` folds a CSV of asset ids into the bank:

    ~/anaconda3/python.exe quiz/pipeline/import_ml_csv.py macaulay_image_urls.csv
    ~/anaconda3/python.exe quiz/pipeline/fetch_photos.py --sync

It reads `taxon`, `asset_id`, `rating`, `photographer`, `license`, `location`,
and `variant` if the file has one. Three things it fixes on the way in:

- **The same photograph in two banks.** A bird tagged `immature` also comes
  back from the unfiltered search, so without care one asset sits in both the
  `any` and `immature` banks - drawn twice as often, and labelled `immature`
  one time and `any` the next. The most specific tag wins and the rest are
  dropped. On the first full variant harvest that was 4,844 rows.

- **The rating skew.** A harvester that asks for 50 and keeps 50 returns the 50
  best-rated, and a bank of five-star photographs is a bank of perched adults in
  golden hour — the one bird nobody has trouble with. This samples across rating
  bands instead of taking the top. It cannot invent spread that is not in the
  file, though: **ask for a much larger pool than you keep** (500, say) and let
  the importer cut it down.
- **The Mexican flag.** The `region` column often comes through empty while
  `location` holds a stringified dict with the country code in it, so the flag
  is recovered from there.

Named variants get a smaller bank than the unfiltered search (15 against 50),
which is what stops 477 species with variants tripling the file.

The importer **never trades down**: an import that would shrink a species
leaves it alone, so a partial or crashed harvest cannot wipe a good bank. That
rule also blocks a legitimate shrink, which is what deduplication is - so pass
`--rebuild` to ignore the cache and build it from the CSV alone:

    ~/anaconda3/python.exe quiz/pipeline/import_ml_csv.py macaulay_image_urls.csv --rebuild

Only safe when the CSV covers every species in the cache. Check with
`plumage.py --bank` afterwards.

## Pinning photographs by hand

Macaulay's search API sits behind a bot gate. A script cannot pass it, and the
harvester only reached 192 species before it came down. The **image CDN is
open**, though, so any Macaulay photograph still works in the quiz given its
asset number.

So: find photographs in your own browser, and paste their numbers into
`/edit`. The box takes any form you end up with on the clipboard - a bare
number, `ML624095658`, a full asset URL, or a mix separated by spaces or
newlines. Anything under six digits is ignored, so a stray year in the pasted
text cannot become a broken photograph. Each pin shows a thumbnail, because an
asset number is not something you can check by eye.

Pinned photographs **replace** the harvested ones for that species - a
photograph you chose is a stronger signal than anything a sampler picked. Press
**Save pins to the repo** to write `src/lib/data/quiz/photo_pins.json`, which
survives a rebuild. That button needs `npm run dev`: the site is prerendered to
static files with no server behind it, so the write endpoint is Vite middleware
and exists in development only. Away from it, **Download the file** and drop it
in by hand.

Worth spending the effort on the pairs where photo choice actually decides the
question - the pewees, the *Empidonax*, the kingbirds - rather than on species
you separate at a glance.

## Writing pair notes in the app

Open **`/edit`**, search for a species, and you get the species worth
comparing it against, each with a box for the note. Notes save to the browser
immediately and the quiz uses them at once; press **Save notes to the repo** to
write `src/lib/data/quiz/pair_notes.json`. Same dev-server caveat as the pins.

Writing a batch is usually faster as a throwaway Python script that loads the
JSON, adds keys, and writes it back — `assert '|'.join(sorted(key.split('|')))
== key` on every key, or the quiz will never find the note. Keep such a script
pure ASCII and build the em dash with `chr(8212)`: a literal one written through
a bash heredoc gets mangled.

## Files you are meant to edit

- `src/lib/data/quiz/pair_notes.json` — the notes. The reason the quiz exists.
- `data/plumage_classes.csv` — which species need sex or age banks.
- `data/empid_traits.csv` — the flycatcher trait table, hand-transcribed and
  worth checking. Buff-breasted forehead angle and Dusky tail length were
  judgement calls.
- `src/lib/data/quiz/photo_pins.json` — written by `/edit`, but plain
  enough to edit by hand.

## Known gap

The notes are the gap now, not the photographs. 362 of the 2,014 same-genus
pairs in the bank have one. Nine genera are complete — Buteogallus, Catharus,
Chordeiles, Columbina, Myiarchus, Piranga, Trogon, Turdus and Tyrannus — and
Empidonax, Setophaga and Vireo have their confusable clusters covered. The
biggest holes are the ones you would expect: **Setophaga** (239 pairs
unwritten, though most of those are warbler pairs nobody confuses),
**Icterus** (16 species, 120 pairs), **Vireo** (113), **Calidris** (78) and
**Larus** (66).

The orioles are the ones to do next, because they are a daily Chiapas problem
*and* because they now have sexed photographs the notes do not yet describe.
