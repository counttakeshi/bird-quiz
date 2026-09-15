<script lang="ts">
	import indexData from '$lib/data/quiz/index.json';
	import {
		search,
		suggestions,
		makeQuestion,
		type SpeciesEntry,
		type Pick,
		type Question
	} from '$lib/quiz/engine';
	import { photosFor, hasPhotos, variantsFor, hasFlight } from '$lib/quiz/photos';
	import { VARIANT_ORDER, satisfiesVariant, type PlumageVariant } from '$lib/quiz/pins';
	import { loadNotes, noteFor, type NoteMap } from '$lib/quiz/notes';
	import { base } from '$app/paths';
	import { dev } from '$app/environment';

	const index = indexData as SpeciesEntry[];
	const byCode = new Map(index.map((e) => [e.c, e]));
	const withPhotos = index.filter((e) => hasPhotos(e.c));

	let screen = $state<'setup' | 'quiz'>('setup');

	function name(code: string): string {
		return byCode.get(code)?.n ?? code;
	}

	// ── choosing species ──────────────────────────────────────────────────────

	let query = $state('');
	let highlighted = $state(0);
	let picks = $state<Pick[]>([]);
	let inputEl = $state<HTMLInputElement | null>(null);

	const matches = $derived(query.trim() ? search(withPhotos, query) : []);
	const open = $derived(matches.length > 0);
	const chosen = $derived(picks.map((p) => p.code));
	const suggested = $derived(suggestions(withPhotos, chosen));
	const ready = $derived(picks.length >= 2);

	function add(code: string) {
		if (!chosen.includes(code)) picks = [...picks, { code, variants: [], flight: false }];
		query = '';
		highlighted = 0;
		inputEl?.focus();
	}

	function remove(code: string) {
		picks = picks.filter((p) => p.code !== code);
	}

	/** Toggle one plumage for one species. None selected means all of them. */
	function toggleVariant(code: string, variant: PlumageVariant) {
		picks = picks.map((p) => {
			if (p.code !== code) return p;
			const on = p.variants.includes(variant);
			return { ...p, variants: on ? p.variants.filter((v) => v !== variant) : [...p.variants, variant] };
		});
	}

	/** Narrow to birds in the air. Combines with the plumage above, so you can
	 *  ask for a juvenile in flight rather than one or the other. */
	function toggleFlight(code: string) {
		picks = picks.map((p) => (p.code === code ? { ...p, flight: !p.flight } : p));
	}

	/** A photograph satisfies a pick when the plumage matches and, if flight
	 *  was asked for, the bird is airborne. */
	function allows(pick: Pick, photo: Shows): boolean {
		if (pick.flight && !photo.flight) return false;
		if (!pick.variants.length) return true;
		return pick.variants.some((w) => photo.variants.some((v) => satisfiesVariant(v, w)));
	}

	function onKeydown(event: KeyboardEvent) {
		if (!open) return;
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			highlighted = (highlighted + 1) % matches.length;
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			highlighted = (highlighted - 1 + matches.length) % matches.length;
		} else if (event.key === 'Enter') {
			event.preventDefault();
			add(matches[highlighted].entry.c);
		} else if (event.key === 'Escape') {
			query = '';
		}
	}

	// ── playing ───────────────────────────────────────────────────────────────

	/** What a photograph shows, which is what the engine filters and reports. */
	type Shows = { variants: PlumageVariant[]; flight: boolean };

	let question = $state<Question<Shows> | null>(null);
	let answered = $state<string | null>(null);
	let notes = $state<NoteMap>({});

	$effect(() => {
		notes = loadNotes();
	});

	const photo = $derived(
		question ? (photosFor(question.target)[question.photo] ?? null) : null
	);

	/**
	 * The notes for the comparison you just made.
	 *
	 * Wrong answer: the pair you actually confused. Right answer: every other
	 * species on the board, since any of them could have caught you out.
	 */
	const shown = $derived.by(() => {
		const q = question;
		if (!q || !answered) return [];
		const target = q.target;
		const others =
			answered !== target ? [answered] : q.options.filter((c) => c !== target);
		return others
			.map((code) => ({ code, text: noteFor(notes, target, code) }))
			.filter((n): n is { code: string; text: string } => Boolean(n.text));
	});

	/** Split "primary projection: Alder long, Willow medium" into label and body. */
	function rows(text: string): { label: string; body: string }[] {
		return text.split('\n').map((line) => {
			const at = line.indexOf(':');
			const dash = line.indexOf('—');
			const cut = dash > -1 && (dash < at || at < 0) ? dash : at;
			return cut > -1 && cut < 34
				? { label: line.slice(0, cut).trim(), body: line.slice(cut + 1).trim() }
				: { label: '', body: line.trim() };
		});
	}

	function start() {
		screen = 'quiz';
		question = null;
		next();
	}

	function next() {
		answered = null;
		question = makeQuestion(
			picks,
			(code): Shows[] => photosFor(code).map((p) => ({ variants: p.variants, flight: p.flight })),
			allows,
			question?.target
		);
	}

	function answer(code: string) {
		if (answered || !question) return;
		answered = code;
	}

</script>

<svelte:head>
	<title>Photo quiz</title>
	<meta name="description" content="Compare confusion species side by side." />
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="wrap">
	{#if screen === 'setup'}
		<header class="intro">
			<h1>Photo quiz</h1>
			<p>Pick two or more birds.</p>
			{#if dev}
				<p class="links"><a href="{base}/edit">Edit the notes and photographs</a></p>
			{/if}
		</header>

		<div class="picker">
			<label for="species-search">Search by English, scientific or Spanish name</label>
			<div class="combo">
				<input
					id="species-search"
					bind:this={inputEl}
					bind:value={query}
					onkeydown={onKeydown}
					type="text"
					autocomplete="off"
					role="combobox"
					aria-expanded={open}
					aria-controls="species-listbox"
					aria-autocomplete="list"
					placeholder="Acadian Flycatcher, Contopus, Papamoscas…"
				/>
				{#if open}
					<ul id="species-listbox" role="listbox">
						{#each matches as match, i (match.entry.c)}
							<li role="option" aria-selected={i === highlighted}>
								<button
									type="button"
									class:active={i === highlighted}
									onmouseenter={() => (highlighted = i)}
									onclick={() => add(match.entry.c)}
								>
									<span class="opt-name">{match.entry.n}</span>
									<span class="opt-meta">
										{#if match.via === 'spanish' && match.entry.e}
											{match.entry.e}
										{:else}
											<i>{match.entry.s}</i>
										{/if}
									</span>
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</div>

		{#if picks.length}
			<ul class="chosen">
				{#each picks as pick (pick.code)}
					{@const available = variantsFor(pick.code)}
					{@const flyable = hasFlight(pick.code)}
					<li>
						<div class="head">
							<strong>{name(pick.code)}</strong>
							<button type="button" class="x" onclick={() => remove(pick.code)}>Remove</button>
						</div>
						{#if available.length > 1 || flyable}
							<div class="variants">
								{#if available.length > 1}
									<button
										type="button"
										class:on={pick.variants.length === 0}
										onclick={() => (picks = picks.map((p) => (p.code === pick.code ? { ...p, variants: [] } : p)))}
									>All</button>
									{#each VARIANT_ORDER.filter((v) => available.includes(v)) as variant (variant)}
										<button
											type="button"
											class:on={pick.variants.includes(variant)}
											onclick={() => toggleVariant(pick.code, variant)}
										>{variant}</button>
									{/each}
								{/if}
								{#if flyable}
									<button
										type="button"
										class="posture"
										class:on={pick.flight}
										onclick={() => toggleFlight(pick.code)}
									>in flight</button>
								{/if}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}

		{#if suggested.length}
			<div class="suggest">
				<h2>Often confused with these</h2>
				<ul>
					{#each suggested as s (s.entry.c)}
						<li>
							<button type="button" onclick={() => add(s.entry.c)}>
								<span>{s.entry.n}</span>
								<span class="why">{s.why}</span>
							</button>
						</li>
					{/each}
				</ul>
			</div>
		{/if}

		<button class="go" type="button" disabled={!ready} onclick={start}>
			{ready ? `Compare these ${picks.length}` : 'Pick at least two'}
		</button>
	{:else if question}
		<div class="hud">
			<span class="tier">{picks.length} species</span>
			<button type="button" class="quit" onclick={() => (screen = 'setup')}>Change</button>
		</div>

		<figure class="plate">
			{#if photo}
				<img src={photo.src} alt="Unidentified bird" />
				<figcaption>
					<span>
						{photo.credit}
						{#if photo.source === 'macaulay'}
							<span class="holder">Cornell Lab of Ornithology · Macaulay Library</span>
						{:else}
							<span class="holder">iNaturalist</span>
						{/if}
						{#if photo.rating !== undefined}<span class="stars">{photo.rating.toFixed(1)}★</span>{/if}
					</span>
					<a href={photo.href} target="_blank" rel="noopener noreferrer">
						{photo.source === 'macaulay' ? 'Macaulay' : 'iNaturalist'} ↗
					</a>
				</figcaption>
			{/if}
		</figure>

		<div class="options">
			{#each question.options as code (code)}
				<button
					type="button"
					class="option"
					class:correct={answered && code === question.target}
					class:wrong={answered === code && code !== question.target}
					disabled={!!answered}
					onclick={() => answer(code)}
				>
					{name(code)}
				</button>
			{/each}
		</div>

		{#if answered}
			<div class="feedback" class:right={answered === question.target}>
				<strong>
					{#if answered === question.target}
						{name(question.target)}
					{:else}
						{name(question.target)}, not {name(answered)}
					{/if}
				</strong>
				{#if photo && (photo.variants.length || photo.flight)}
					<span class="revealed">
						{[...photo.variants, ...(photo.flight ? ['in flight'] : [])].join(', ')}
					</span>
				{/if}

				{#each shown as note (note.code)}
					<div class="note">
						<h3>vs {name(note.code)}</h3>
						<dl>
							{#each rows(note.text) as row (row.label + row.body)}
								{#if row.label}
									<dt>{row.label}</dt>
									<dd>{row.body}</dd>
								{:else}
									<dd class="plain">{row.body}</dd>
								{/if}
							{/each}
						</dl>
					</div>
				{/each}

				{#if !shown.length}
					<p class="measured">
						No notes yet.{#if dev} <a href="{base}/edit">Write them →</a>{/if}
					</p>
				{/if}

				<button type="button" class="go" onclick={next}>Next bird</button>
			</div>
		{/if}
	{:else}
		<p class="empty">No photographs for those species yet.</p>
		<button type="button" class="go" onclick={() => (screen = 'setup')}>Back</button>
	{/if}
</div>

<style>
	.wrap {
		max-width: 46rem;
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

	/* ── picker ───────────────────────────────────────────────────────────── */

	.links {
		margin-top: 0.9rem;
		font-size: 0.9rem;
	}
	.links a {
		color: var(--canopy);
	}

	.note {
		margin-top: 0.9rem;
		padding: 0.6rem 0.8rem;
		border-left: 3px solid var(--rule);
		background: var(--white);
		color: var(--stone);
		font-size: 0.85rem;
		line-height: 1.5;
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
		padding: 0.85rem 1rem;
		font: inherit;
		font-size: 1.05rem;
		color: var(--ink);
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.4rem;
	}
	.combo input:focus {
		outline: 2px solid var(--phwa);
		outline-offset: 1px;
	}

	#species-listbox {
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
	#species-listbox button {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
		width: 100%;
		padding: 0.6rem 0.9rem;
		background: none;
		border: 0;
		text-align: left;
		cursor: pointer;
		font: inherit;
	}
	#species-listbox button.active {
		background: var(--mist);
	}
	.opt-name {
		color: var(--ink);
	}
	.opt-meta {
		color: var(--stone);
		font-size: 0.85rem;
	}

	/* ── modes ────────────────────────────────────────────────────────────── */

	/* ── the plan, shown before you start ─────────────────────────────────── */

	/* The bird you picked, so it reads as the anchor rather than one of a crowd. */

	.measured {
		font-size: 0.85rem;
		font-style: italic;
	}

	.revealed {
		margin: 0.5rem 0 0;
		font-weight: 700;
		color: var(--canopy);
	}

	.chosen {
		list-style: none;
		margin: 1.25rem 0 0;
	}
	.chosen li {
		padding: 0.6rem 0;
		border-bottom: 1px solid var(--rule);
	}
	.chosen .head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
	}
	.chosen strong {
		color: var(--ink);
	}
	.chosen .x {
		background: none;
		border: 0;
		padding: 0;
		font: inherit;
		font-size: 0.82rem;
		color: var(--stone);
		cursor: pointer;
		text-decoration: underline;
	}
	.variants {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin-top: 0.45rem;
	}
	.variants button {
		padding: 0.2rem 0.6rem;
		border: 1px solid var(--rule);
		border-radius: 999px;
		background: var(--white);
		font: inherit;
		font-size: 0.8rem;
		color: var(--stone);
		cursor: pointer;
	}
	/* Flight narrows whatever plumage is selected rather than replacing it, so
	   it is set apart from the pills it combines with. */
	.variants button.posture {
		margin-left: 0.5rem;
		border-style: dashed;
	}

	.variants button.on {
		background: var(--canopy);
		border-color: var(--canopy);
		color: var(--white);
	}

	.suggest {
		margin-top: 2rem;
	}
	.suggest h2 {
		font-family: var(--display);
		font-weight: 400;
		font-size: 1.15rem;
		color: var(--ink);
	}
	.suggest ul {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		list-style: none;
		margin-top: 0.75rem;
	}
	.suggest button {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		padding: 0.4rem 0.75rem;
		border: 1px solid var(--rule);
		border-radius: 0.4rem;
		background: var(--white);
		font: inherit;
		font-size: 0.88rem;
		color: var(--ink);
		cursor: pointer;
		text-align: left;
	}
	.suggest button:hover {
		border-color: var(--canopy);
	}
	.suggest .why {
		font-size: 0.75rem;
		font-style: italic;
		color: var(--stone);
	}

	/* One note per rival, marks as a definition list rather than a wall of
	   lines - the label carries the eye, the value sits beside it. */
	.note {
		margin-top: 1rem;
	}
	.note h3 {
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--stone);
		margin-bottom: 0.4rem;
	}
	.note dl {
		display: grid;
		grid-template-columns: minmax(7rem, auto) 1fr;
		gap: 0.15rem 0.9rem;
		font-size: 0.92rem;
	}
	.note dt {
		color: var(--stone);
		text-align: right;
	}
	.note dd {
		color: var(--ink);
		margin: 0;
	}
	.note dd.plain {
		grid-column: 1 / -1;
		margin-top: 0.3rem;
	}

	.go:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.go {
		display: inline-block;
		padding: 0.7rem 1.3rem;
		background: var(--phwa);
		color: var(--white);
		border: 0;
		border-radius: 0.35rem;
		font: inherit;
		font-weight: 700;
		cursor: pointer;
	}

	/* ── runtime ──────────────────────────────────────────────────────────── */

	.hud {
		display: flex;
		align-items: center;
		gap: 1rem;
		font-size: 0.85rem;
		color: var(--stone);
	}
	.hud .tier {
		font-weight: 700;
		color: var(--canopy);
	}
	.quit {
		background: none;
		border: 1px solid var(--rule);
		border-radius: 0.3rem;
		padding: 0.3rem 0.7rem;
		font: inherit;
		font-size: 0.85rem;
		color: var(--stone);
		cursor: pointer;
	}

	.plate {
		margin: 1rem 0 1.25rem;
		background: var(--mist);
		border-radius: 0.5rem;
		overflow: hidden;
	}
	.plate img {
		display: block;
		width: 100%;
		aspect-ratio: 4 / 3;
		object-fit: cover;
	}
	.plate figcaption {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		color: var(--stone);
	}
	.stars {
		margin-left: 0.35rem;
		color: var(--canopy);
		white-space: nowrap;
	}

	/* Cornell asks for the rights holder alongside the photographer, not just
	   the name: "Species © Contributor; Cornell Lab of Ornithology | Macaulay
	   Library". Quieter than the photographer, who is the person being
	   credited, but present. */
	.holder {
		margin-left: 0.35rem;
		color: var(--stone);
	}

	.plate figcaption a {
		color: var(--canopy);
		white-space: nowrap;
	}

	.options {
		display: grid;
		gap: 0.6rem;
		grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
	}
	.option {
		padding: 0.85rem 1rem;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.4rem;
		font: inherit;
		color: var(--ink);
		cursor: pointer;
		text-align: left;
	}
	.option:hover:not(:disabled) {
		border-color: var(--canopy);
	}
	.option.correct {
		background: var(--canopy);
		border-color: var(--canopy);
		color: var(--white);
	}
	.option.wrong {
		background: var(--phwa);
		border-color: var(--phwa);
		color: var(--white);
	}

	.feedback {
		margin-top: 1.25rem;
		padding: 1rem 1.1rem;
		border-left: 3px solid var(--phwa);
		background: var(--white);
	}
	.feedback.right {
		border-left-color: var(--canopy);
	}
	.feedback p {
		color: var(--stone);
		margin: 0.5rem 0 1rem;
		line-height: 1.55;
	}

</style>
