<script lang="ts">
	import indexData from '$lib/data/quiz/index.json';
	import { search, suggestions, type SpeciesEntry } from '$lib/quiz/engine';
	import { photoCount } from '$lib/quiz/photos';
	import {
		loadPins,
		savePins,
		prunePins,
		countPins,
		parseAssets,
		VARIANT_ORDER,
		type PinMap,
		type PlumageVariant
	} from '$lib/quiz/pins';
	import {
		loadNotes,
		saveNotes,
		pruneNotes,
		countNotes,
		pairKey,
		type NoteMap
	} from '$lib/quiz/notes';
	import { base } from '$app/paths';

	const index = indexData as SpeciesEntry[];
	const byCode = new Map(index.map((e) => [e.c, e]));

	let subject = $state<string | null>(null);
	let query = $state('');
	const matches = $derived(query.trim() ? search(index, query, 8) : []);

	function name(code: string): string {
		return byCode.get(code)?.n ?? code;
	}

	/** Who to write notes against: congeners first, then the family. */
	const related = $derived(subject ? suggestions(index, [subject], 20) : []);

	// ── notes ─────────────────────────────────────────────────────────────────

	let notes = $state<NoteMap>({});
	$effect(() => {
		notes = loadNotes();
	});

	function noteText(code: string): string {
		return subject ? (notes[pairKey(subject, code)] ?? '') : '';
	}

	function setNote(code: string, text: string) {
		if (!subject) return;
		notes = pruneNotes({ ...notes, [pairKey(subject, code)]: text });
		saveNotes(notes);
		notesSaved = false;
	}

	let notesSaved = $state(false);
	let notesError = $state<string | null>(null);

	async function saveNotesToDisk() {
		notesError = null;
		try {
			const res = await fetch('/__quiz-pair-notes', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(pruneNotes(notes), null, '\t')
			});
			if (!res.ok) throw new Error(await res.text());
			notesSaved = true;
		} catch (err) {
			notesError =
				err instanceof Error && err.message
					? err.message
					: 'No dev server - run `npm run dev` to save into the repo.';
		}
	}

	// ── pinned photographs ────────────────────────────────────────────────────

	let pins = $state<PinMap>({});
	let paste = $state('');
	let photographer = $state('');
	let pasteVariant = $state<PlumageVariant>('any');

	$effect(() => {
		pins = loadPins();
	});

	const pinned = $derived(subject ? (pins[subject] ?? []) : []);
	const incoming = $derived(parseAssets(paste).filter((a) => !pinned.some((p) => p.a === a)));

	function addPins() {
		if (!subject || !incoming.length) return;
		pins = prunePins({
			...pins,
			[subject]: [
				...pinned,
				...incoming.map((a) => ({
					a,
					...(photographer.trim() ? { by: photographer.trim() } : {}),
					...(pasteVariant !== 'any' ? { v: pasteVariant } : {})
				}))
			]
		});
		savePins(pins);
		paste = '';
		pinsSaved = false;
	}

	function removePin(asset: number) {
		if (!subject) return;
		pins = prunePins({ ...pins, [subject]: pinned.filter((p) => p.a !== asset) });
		savePins(pins);
		pinsSaved = false;
	}

	let pinsSaved = $state(false);
	let pinsError = $state<string | null>(null);

	async function savePinsToDisk() {
		pinsError = null;
		try {
			const res = await fetch('/__quiz-photo-pins', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(prunePins(pins), null, '\t')
			});
			if (!res.ok) throw new Error(await res.text());
			pinsSaved = true;
		} catch (err) {
			pinsError =
				err instanceof Error && err.message
					? err.message
					: 'No dev server - run `npm run dev` to save into the repo.';
		}
	}
</script>

<svelte:head>
	<title>Edit quiz notes</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="wrap">
	<header class="intro">
		<h1>Quiz notes and photographs</h1>
		<p class="links">
			<a href="{base}/">← Back to the quiz</a>
			{#if countNotes(notes)}<span class="count">{countNotes(notes)} notes</span>{/if}
			{#if countPins(pins)}<span class="count">{countPins(pins)} pinned</span>{/if}
		</p>
	</header>

	<div class="picker">
		<label for="subject-search">Which species?</label>
		<div class="combo">
			<input
				id="subject-search"
				bind:value={query}
				type="text"
				autocomplete="off"
				placeholder="Acadian Flycatcher, Empidonax…"
			/>
			{#if matches.length}
				<ul class="listbox">
					{#each matches as match (match.entry.c)}
						<li>
							<button
								type="button"
								onclick={() => {
									subject = match.entry.c;
									query = '';
								}}
							>
								<span>{match.entry.n}</span>
								<span class="meta"><i>{match.entry.s}</i></span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</div>

	{#if subject}
		<section class="block">
			<h2>How to tell {name(subject)} apart</h2>
			<ul class="note-list">
				{#each related as rel (rel.entry.c)}
					<li>
						<label>
							<span class="who">
								vs <strong>{rel.entry.n}</strong>
								<span class="tag dim">{rel.why}</span>
							</span>
							<textarea
								rows="2"
								placeholder="primary projection: long and even; lower mandible wholly orange"
								value={noteText(rel.entry.c)}
								onchange={(e) => setNote(rel.entry.c, e.currentTarget.value)}
							></textarea>
						</label>
					</li>
				{/each}
			</ul>
			<div class="row">
				<button type="button" class="go alt" onclick={saveNotesToDisk}>Save notes</button>
			</div>
			{#if notesSaved}<p class="ok">Saved to pair_notes.json.</p>{/if}
			{#if notesError}<p class="warn">{notesError}</p>{/if}
		</section>

		<section class="block">
			<h2>Photographs for {name(subject)}</h2>
			<p class="sub">
				{photoCount(subject)} in the bank. Paste Macaulay asset numbers to add your own —
				<strong>ML624095658</strong>, a bare number, or a whole asset link.
			</p>

			<textarea bind:value={paste} rows="3" placeholder="ML624095658, ML640146019"></textarea>
			<div class="row">
				<select bind:value={pasteVariant}>
					{#each ['any', ...VARIANT_ORDER] as variant (variant)}
						<option value={variant}>{variant === 'any' ? 'unspecified plumage' : variant}</option>
					{/each}
				</select>
				<input bind:value={photographer} type="text" placeholder="Photographer (optional)" />
			</div>
			<button type="button" class="go" disabled={!incoming.length} onclick={addPins}>
				{incoming.length ? `Pin ${incoming.length}` : 'Paste asset numbers'}
			</button>

			{#if pinned.length}
				<ul class="pin-list">
					{#each pinned as pin (pin.a)}
						<li>
							<img src="https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{pin.a}/320" alt="" />
							<span>
								<a href="https://macaulaylibrary.org/asset/{pin.a}" target="_blank" rel="noopener noreferrer">ML{pin.a}</a>
								{#if pin.v}<span class="tag">{pin.v}</span>{/if}
								{#if pin.by}<span class="who">{pin.by}</span>{/if}
							</span>
							<button type="button" class="x" onclick={() => removePin(pin.a)}>Remove</button>
						</li>
					{/each}
				</ul>
				<div class="row">
					<button type="button" class="go alt" onclick={savePinsToDisk}>Save pins</button>
				</div>
				{#if pinsSaved}<p class="ok">Saved to photo_pins.json.</p>{/if}
				{#if pinsError}<p class="warn">{pinsError}</p>{/if}
			{/if}
		</section>
	{/if}
</div>

<style>
	.wrap {
		max-width: 52rem;
		margin: 0 auto;
		padding: 2.5rem 1.5rem 5rem;
	}

	.intro h1 {
		font-family: var(--display);
		font-weight: 400;
		font-size: 2.25rem;
		color: var(--ink);
	}
	.intro p,
	.sub {
		color: var(--stone);
		margin-top: 0.75rem;
		line-height: 1.6;
	}
	.links {
		display: flex;
		align-items: center;
		gap: 1rem;
		font-size: 0.9rem;
	}
	.links a {
		color: var(--canopy);
	}
	.count {
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		background: var(--canopy);
		color: var(--white);
		font-size: 0.78rem;
	}

	.picker {
		margin-top: 2rem;
	}
	.picker > label {
		display: block;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--stone);
		margin-bottom: 0.5rem;
	}
	.combo {
		position: relative;
	}
	.combo input {
		width: 100%;
		padding: 0.75rem 1rem;
		font: inherit;
		color: var(--ink);
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.4rem;
	}
	.combo input:focus {
		outline: 2px solid var(--phwa);
		outline-offset: 1px;
	}
	.listbox {
		position: absolute;
		z-index: 20;
		inset-inline: 0;
		top: calc(100% + 0.25rem);
		list-style: none;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.4rem;
		box-shadow: 0 8px 24px rgb(22 36 31 / 0.12);
		overflow: hidden;
	}
	.listbox button {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
		width: 100%;
		padding: 0.55rem 0.9rem;
		background: none;
		border: 0;
		text-align: left;
		cursor: pointer;
		font: inherit;
		color: var(--ink);
	}
	.listbox button:hover {
		background: var(--mist);
	}
	.meta {
		color: var(--stone);
		font-size: 0.85rem;
	}

	.block {
		margin-top: 2.5rem;
		padding-top: 2rem;
		border-top: 1px solid var(--rule);
	}
	.block h2 {
		font-family: var(--display);
		font-weight: 400;
		font-size: 1.5rem;
		color: var(--ink);
	}

	.note-list {
		list-style: none;
		margin: 1.25rem 0 0;
	}
	.note-list li {
		padding: 0.5rem 0;
		border-bottom: 1px solid var(--rule);
	}
	.who {
		display: block;
		margin-bottom: 0.3rem;
		font-size: 0.9rem;
		color: var(--stone);
	}
	.who strong {
		color: var(--ink);
	}

	textarea,
	.row input[type='text'],
	.row select {
		font: inherit;
		font-size: 0.9rem;
		color: var(--ink);
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
		padding: 0.5rem 0.7rem;
	}
	textarea {
		display: block;
		width: 100%;
		margin-top: 0.75rem;
		resize: vertical;
	}
	.note-list textarea {
		margin-top: 0;
	}

	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem;
		margin-top: 0.75rem;
	}
	.row input[type='text'] {
		flex: 1;
		min-width: 12rem;
	}

	.tag {
		display: inline-block;
		margin-left: 0.35rem;
		padding: 0.02rem 0.35rem;
		border-radius: 0.2rem;
		background: var(--canopy);
		color: var(--white);
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.tag.dim {
		background: var(--mist);
		color: var(--stone);
		font-style: italic;
		text-transform: none;
		letter-spacing: 0;
	}

	.pin-list {
		list-style: none;
		margin: 1.25rem 0 0;
	}
	.pin-list li {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.4rem 0;
		border-bottom: 1px solid var(--rule);
		font-size: 0.9rem;
	}
	.pin-list img {
		width: 3.5rem;
		height: 3.5rem;
		object-fit: cover;
		border-radius: 0.3rem;
		background: var(--mist);
	}
	.pin-list span {
		flex: 1;
	}
	.pin-list a {
		color: var(--canopy);
	}

	.go {
		margin-top: 0.9rem;
		padding: 0.7rem 1.3rem;
		background: var(--phwa);
		color: var(--white);
		border: 0;
		border-radius: 0.35rem;
		font: inherit;
		font-weight: 700;
		cursor: pointer;
	}
	.go.alt {
		background: var(--canopy);
	}
	.go:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.x {
		background: none;
		border: 1px solid var(--rule);
		border-radius: 0.25rem;
		padding: 0.2rem 0.5rem;
		font: inherit;
		font-size: 0.82rem;
		color: var(--phwa);
		cursor: pointer;
	}
	.ok {
		margin-top: 0.9rem;
		color: var(--canopy);
		font-size: 0.88rem;
	}
	.warn {
		margin-top: 0.9rem;
		padding: 0.6rem 0.8rem;
		border-left: 3px solid var(--phwa);
		background: var(--white);
		color: var(--stone);
		font-size: 0.85rem;
	}
</style>
