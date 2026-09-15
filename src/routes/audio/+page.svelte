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
	import { recordingsFor, hasAudio, soundTypesFor, type SoundType } from '$lib/quiz/audio';
	import { loadNotes, noteFor, type NoteMap } from '$lib/quiz/notes';
	import { base } from '$app/paths';

	const index = indexData as SpeciesEntry[];
	const byCode = new Map(index.map((e) => [e.c, e]));
	const withAudio = index.filter((e) => hasAudio(e.c));

	let screen = $state<'setup' | 'quiz'>('setup');

	function name(code: string): string {
		return byCode.get(code)?.n ?? code;
	}

	// ── choosing species ──────────────────────────────────────────────────────

	let query = $state('');
	let highlighted = $state(0);
	let picks = $state<Pick<SoundType>[]>([]);
	let inputEl = $state<HTMLInputElement | null>(null);

	const matches = $derived(query.trim() ? search(withAudio, query) : []);
	const open = $derived(matches.length > 0);
	const chosen = $derived(picks.map((p) => p.code));
	const suggested = $derived(suggestions(withAudio, chosen));
	const ready = $derived(picks.length >= 2);

	function add(code: string) {
		if (!chosen.includes(code)) picks = [...picks, { code, variants: [] }];
		query = '';
		highlighted = 0;
		inputEl?.focus();
	}

	function remove(code: string) {
		picks = picks.filter((p) => p.code !== code);
	}

	/** Toggle song or call for one species. None selected means either. */
	function toggleType(code: string, kind: SoundType) {
		picks = picks.map((p) => {
			if (p.code !== code) return p;
			const on = p.variants.includes(kind);
			return { ...p, variants: on ? p.variants.filter((v) => v !== kind) : [...p.variants, kind] };
		});
	}

	function allows(pick: Pick<SoundType>, kind: SoundType): boolean {
		return !pick.variants.length || pick.variants.includes(kind);
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

	let question = $state<Question<SoundType> | null>(null);
	let answered = $state<string | null>(null);
	let notes = $state<NoteMap>({});
	let player = $state<HTMLAudioElement | null>(null);

	$effect(() => {
		notes = loadNotes();
	});

	const recording = $derived(
		question ? (recordingsFor(question.target)[question.photo] ?? null) : null
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
		const others = answered !== target ? [answered] : q.options.filter((c) => c !== target);
		return others
			.map((code) => ({ code, text: noteFor(notes, target, code) }))
			.filter((n): n is { code: string; text: string } => Boolean(n.text));
	});

	/** Split "voice — Nutting's: a sharp wheek" into label and body. */
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
			(code): SoundType[] => recordingsFor(code).map((r) => r.kind),
			allows,
			question?.target
		);
	}

	function answer(code: string) {
		if (answered || !question) return;
		answered = code;
	}

	function seconds(total: number): string {
		const m = Math.floor(total / 60);
		const s = total % 60;
		return `${m}:${String(s).padStart(2, '0')}`;
	}
</script>

<svelte:head>
	<title>Audio quiz</title>
	<meta name="description" content="Tell confusion species apart by voice." />
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="wrap">
	{#if screen === 'setup'}
		<header class="intro">
			<h1>Audio quiz</h1>
			<p>Pick two or more birds.</p>
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

			<ul class="chosen">
				{#each picks as pick (pick.code)}
					{@const kinds = soundTypesFor(pick.code)}
					<li>
						<div class="head">
							<strong>{name(pick.code)}</strong>
							<button type="button" class="x" onclick={() => remove(pick.code)}>Remove</button>
						</div>
						{#if kinds.length > 1}
							<div class="variants">
								<button
									type="button"
									class:on={pick.variants.length === 0}
									onclick={() =>
										(picks = picks.map((p) =>
											p.code === pick.code ? { ...p, variants: [] } : p
										))}
								>All</button>
								{#each kinds as kind (kind)}
									<button
										type="button"
										class:on={pick.variants.includes(kind)}
										onclick={() => toggleType(pick.code, kind)}
									>{kind}</button>
								{/each}
							</div>
						{/if}
					</li>
				{/each}
			</ul>

			{#if suggested.length}
				<div class="suggest">
					<h2>Often confused with these</h2>
					<div class="chips">
						{#each suggested as s (s.entry.c)}
							<button type="button" onclick={() => add(s.entry.c)}>
								<span class="opt-name">{s.entry.n}</span>
								<span class="opt-meta">{s.why}</span>
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<button type="button" class="go" disabled={!ready} onclick={start}>
				{ready ? `Compare these ${picks.length}` : 'Pick at least two'}
			</button>
		</div>
	{:else if question}
		<div class="hud">
			<button type="button" class="back" onclick={() => (screen = 'setup')}>← Change birds</button>
		</div>

		{#if recording}
			<figure class="player">
				<!-- svelte-ignore a11y_media_has_caption -->
				<audio
					bind:this={player}
					src={recording.src}
					controls
					autoplay
					preload="auto"
				></audio>
				<figcaption>
					<a href={recording.href} target="_blank" rel="noopener">xeno-canto ↗</a>
					<span>
						{recording.credit}
						{#if recording.quality}· {recording.quality}{/if}
						· {seconds(recording.seconds)}
					</span>
				</figcaption>
			</figure>
		{/if}

		<div class="options">
			{#each question.options as code (code)}
				<button
					type="button"
					class:picked={answered === code}
					class:correct={Boolean(answered) && code === question.target}
					onclick={() => answer(code)}
				>{name(code)}</button>
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
				{#if recording}
					<span class="revealed">{recording.kind}</span>
				{/if}

				{#each shown as note (note.code)}
					<div class="note">
						<h3>vs {name(note.code)}</h3>
						<dl>
							{#each rows(note.text) as row}
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
					<p class="measured">No notes yet.</p>
				{/if}

				<button type="button" class="go" onclick={next}>Next bird</button>
			</div>
		{/if}
	{:else}
		<div class="wrap">
			<p class="measured">
				Nothing to ask with those filters. <a href="{base}/audio" onclick={() => (screen = 'setup')}
					>Change birds</a
				>
			</p>
		</div>
	{/if}
</div>

<style>
	.wrap {
		max-width: 46rem;
		margin: 0 auto;
		padding: 2rem 1rem 3rem;
	}

	.intro h1 {
		margin: 0 0 0.35rem;
	}
	.intro p {
		margin: 0 0 1.5rem;
		color: var(--stone);
	}

	/* ── picker ─────────────────────────────────────────────────────────── */

	.picker label {
		display: block;
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--stone);
		margin-bottom: 0.4rem;
	}

	.combo {
		position: relative;
	}

	.combo input {
		width: 100%;
		padding: 0.7rem 0.85rem;
		font: inherit;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
	}
	.combo input:focus {
		outline: none;
		border-color: var(--phwa);
	}

	#species-listbox {
		position: absolute;
		z-index: 5;
		inset-inline: 0;
		margin: 0.25rem 0 0;
		padding: 0;
		list-style: none;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
		max-height: 17rem;
		overflow-y: auto;
	}

	#species-listbox button,
	.chips button {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		width: 100%;
		padding: 0.55rem 0.85rem;
		background: none;
		border: none;
		font: inherit;
		text-align: left;
		cursor: pointer;
	}
	#species-listbox button.active {
		background: var(--mist);
	}

	.opt-meta {
		color: var(--stone);
		font-size: 0.85rem;
	}

	.chosen {
		list-style: none;
		margin: 1rem 0 0;
		padding: 0;
	}
	.chosen li {
		padding: 0.6rem 0;
		border-bottom: 1px solid var(--rule);
	}
	.chosen .head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
	}
	.x {
		background: none;
		border: none;
		font: inherit;
		font-size: 0.8rem;
		color: var(--stone);
		text-decoration: underline;
		cursor: pointer;
	}

	.variants {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin-top: 0.5rem;
	}
	.variants button {
		padding: 0.2rem 0.6rem;
		font: inherit;
		font-size: 0.8rem;
		background: none;
		border: 1px solid var(--rule);
		border-radius: 1rem;
		color: var(--stone);
		cursor: pointer;
	}
	.variants button.on {
		background: var(--canopy);
		border-color: var(--canopy);
		color: var(--white);
	}

	.suggest {
		margin-top: 1.5rem;
	}
	.suggest h2 {
		font-size: 1rem;
		margin: 0 0 0.6rem;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.chips button {
		width: auto;
		display: block;
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
		padding: 0.45rem 0.7rem;
	}
	.chips button:hover {
		border-color: var(--canopy);
	}
	.chips .opt-meta {
		display: block;
		font-size: 0.75rem;
	}

	.go {
		display: block;
		margin-top: 1.5rem;
		padding: 0.6rem 1.2rem;
		font: inherit;
		background: var(--phwa);
		border: none;
		border-radius: 0.35rem;
		color: var(--white);
		cursor: pointer;
	}
	.go:disabled {
		opacity: 0.5;
		cursor: default;
	}

	/* ── runtime ────────────────────────────────────────────────────────── */

	.hud {
		margin-bottom: 1rem;
	}
	.back {
		background: none;
		border: none;
		font: inherit;
		font-size: 0.85rem;
		color: var(--stone);
		cursor: pointer;
		padding: 0;
	}

	.player {
		margin: 0 0 1.25rem;
	}
	.player audio {
		width: 100%;
	}
	.player figcaption {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 0.4rem;
		font-size: 0.78rem;
		color: var(--stone);
	}

	.options {
		display: grid;
		gap: 0.5rem;
		grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
	}
	.options button {
		padding: 0.8rem 1rem;
		font: inherit;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
		cursor: pointer;
	}
	.options button.correct {
		background: var(--canopy);
		border-color: var(--canopy);
		color: var(--white);
	}
	.options button.picked:not(.correct) {
		border-color: var(--phwa);
	}

	.feedback {
		margin-top: 1.5rem;
		padding-left: 0.9rem;
		border-left: 3px solid var(--phwa);
	}
	.feedback.right {
		border-left-color: var(--canopy);
	}
	.feedback strong {
		display: block;
		font-family: var(--display);
		font-size: 1.15rem;
	}

	.revealed {
		display: inline-block;
		margin-top: 0.2rem;
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--stone);
	}

	.note {
		margin-top: 1.1rem;
	}
	.note h3 {
		font-size: 0.95rem;
		margin: 0 0 0.35rem;
	}
	.note dl {
		margin: 0;
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.15rem 0.8rem;
	}
	.note dt {
		color: var(--stone);
		font-size: 0.85rem;
		text-align: right;
	}
	.note dd {
		margin: 0;
		font-size: 0.9rem;
	}
	.note dd.plain {
		grid-column: 1 / -1;
	}

	.measured {
		color: var(--stone);
		font-size: 0.9rem;
	}
</style>
