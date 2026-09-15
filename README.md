# Bird ID quiz

A study tool for the confusion species of Chiapas: it shows a photograph and
asks which of the birds you picked it is. SvelteKit, prerendered to static
HTML/CSS/JS, hosted on GitHub Pages.

Live: <https://counttakeshi.github.io/bird-quiz/>

Split out of the cardellina.com repo, where it began as a route. It shares no
code with that site now.

## Layout

- `src/routes/+page.svelte` - the quiz itself.
- `src/routes/edit/+page.svelte` - the editor for the notes and photo pins.
  Development only; see below.
- `src/lib/quiz/` - `engine.ts` (species search), `photos.ts` (which photograph
  answers a question), `pins.ts` (plumage variants), `notes.ts` (pair notes).
- `src/lib/data/quiz/` - the data, all four files hand-maintained or generated
  upstream:
  - `index.json` - the species list, keyed by eBird code.
  - `photos.json` - candidate photographs per species.
  - `photo_pins.json` - Macaulay asset numbers pinned by hand.
  - `pair_notes.json` - how to tell two species apart, keyed by the two eBird
    codes sorted and joined with `|`.

Photographs are not in this repo. They stream from the Macaulay and iNaturalist
CDNs, so the quiz needs a connection to ask a question.

## Developing

```sh
npm install
npm run dev -- --open
```

## The editor

`/edit` writes `pair_notes.json` and `photo_pins.json` back into the repo
through Vite middleware that only exists under `npm run dev`. The published
build has no server behind it, so the editor is dropped from it by
`scripts/postbuild.mjs` and the links to it are hidden outside dev. Edit, then
commit the changed JSON like any other source file.

## Building

```sh
npm run check    # typecheck
npm run build    # static output in ./build
npm run preview
```

`BASE_PATH` prefixes every link: empty for a domain root, `/bird-quiz` for the
GitHub Pages project URL. The deploy workflow derives it from the repo name.

On Windows, set it from PowerShell rather than Git Bash - MSYS rewrites a
leading-slash value into a Windows path:

```powershell
$env:BASE_PATH = '/bird-quiz'; npm run build
```

## Deploying

Push to `main`. `.github/workflows/deploy.yml` builds and publishes to GitHub
Pages. Pages must be set to **Settings -> Pages -> Source: GitHub Actions**.

## Not for crawling

The quiz shows other people's photographs under their CC terms, for one
person's practice. `robots.txt` disallows everything and the pages carry
`noindex`. Keep it that way.
