<script lang="ts">
	import '$lib/styles/global.css';
	import { asset } from '$lib/paths';
	import { base } from '$app/paths';
	import { dev } from '$app/environment';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { prefs, loadPrefs, setLang, setNames, nameLang, text, type Lang } from '$lib/i18n.svelte';

	let { children } = $props();

	const SITE = 'https://www.cardellina.com';
	const s = $derived(text());

	// ── language menu ─────────────────────────────────────────────────────────
	// Interface language and bird-name language both live behind the one flag,
	// so neither adds anything to the pages themselves.

	const LANGS: Lang[] = ['es', 'en'];
	const OWN_NAME: Record<Lang, string> = { es: 'Español', en: 'English' };

	let menuOpen = $state(false);
	let prefsEl = $state<HTMLElement | null>(null);
	let triggerEl = $state<HTMLButtonElement | null>(null);

	// composedPath, not contains(): picking an option re-renders the ticks, and
	// a node removed mid-click would read as a click outside.
	function onWindowClick(e: MouseEvent) {
		if (menuOpen && prefsEl && !e.composedPath().includes(prefsEl)) menuOpen = false;
	}

	function onWindowKeydown(e: KeyboardEvent) {
		if (menuOpen && e.key === 'Escape') {
			menuOpen = false;
			triggerEl?.focus();
		}
	}

	function onFocusOut(e: FocusEvent) {
		if (prefsEl && !prefsEl.contains(e.relatedTarget as Node | null)) menuOpen = false;
	}

	onMount(loadPrefs);

	$effect(() => {
		document.documentElement.lang = prefs.lang;
	});

	// The way back to the chooser, on every page except the chooser itself.
	// In the layout rather than in each quiz so the two cannot drift, and so a
	// third quiz gets it for nothing.
	//
	// route.id, not the pathname: the pathname carries the base path, which
	// differs between a domain root and the project URL, and comparing against
	// it put the link on all three pages including the chooser.
	const inQuiz = $derived(page.route.id !== '/');

	// ── installable app ───────────────────────────────────────────────────────
	// Here rather than on a quiz page: the app is both quizzes, and whichever
	// one you happened to open first should not be the one that owns the install.

	let installPrompt = $state<{ prompt: () => void } | null>(null);

	$effect(() => {
		if (!('serviceWorker' in navigator)) return;
		// Not under `npm run dev`: the worker matches cached files ignoring the
		// query string, and Vite serves a component's CSS as the same path with
		// a query, so dev got the JavaScript back as CSS and lost every style.
		// Unregister any copy an earlier dev session left behind.
		if (dev) {
			navigator.serviceWorker.getRegistrations().then((regs) => {
				for (const r of regs) {
					if (r.active?.scriptURL.endsWith('quiz-sw.js')) r.unregister();
				}
			});
			return;
		}
		navigator.serviceWorker.register(asset('quiz-sw.js'), { scope: `${base}/` }).catch(() => {
			/* No offline shell; both quizzes need the network for their media anyway. */
		});
	});

	$effect(() => {
		const onPrompt = (e: Event) => {
			e.preventDefault();
			installPrompt = e as unknown as { prompt: () => void };
		};
		window.addEventListener('beforeinstallprompt', onPrompt);
		return () => window.removeEventListener('beforeinstallprompt', onPrompt);
	});

	function install() {
		installPrompt?.prompt();
		installPrompt = null;
	}
</script>

<svelte:window onclick={onWindowClick} onkeydown={onWindowKeydown} />

<svelte:head>
	<link rel="icon" type="image/png" sizes="32x32" href={asset('favicon-32.png')} />
	<link rel="apple-touch-icon" sizes="180x180" href={asset('apple-touch-icon.png')} />
	<link rel="manifest" href={asset('quiz.webmanifest')} />
	<meta name="theme-color" content="#2f4a3c" />
	<meta name="mobile-web-app-capable" content="yes" />
	<meta name="apple-mobile-web-app-title" content="Bird Quiz" />
</svelte:head>

<header class="bar">
	<a class="brand" href={SITE} target="_blank" rel="noopener">
		<img src={asset('cardellina-logo.webp')} alt="Cardellina Birding Tours" width="40" height="40" />
		<span>cardellina.com</span>
	</a>

	<div class="prefs" bind:this={prefsEl} onfocusout={onFocusOut}>
		<button
			bind:this={triggerEl}
			type="button"
			class="trigger"
			aria-expanded={menuOpen}
			aria-controls="prefs-menu"
			aria-label="{s.language}: {OWN_NAME[prefs.lang]}"
			title={OWN_NAME[prefs.lang]}
			onclick={() => (menuOpen = !menuOpen)}
		>
			{@render flag(prefs.lang, 'trigger')}
			<svg class="chevron" viewBox="0 0 10 6" aria-hidden="true">
				<path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.5" />
			</svg>
		</button>

		{#if menuOpen}
			<div id="prefs-menu" class="menu">
				<div role="group" aria-labelledby="prefs-lang">
					<p id="prefs-lang" class="group-label">{s.language}</p>
					{#each LANGS as lang (lang)}
						<button type="button" aria-pressed={prefs.lang === lang} onclick={() => setLang(lang)}>
							{@render flag(lang, `menu-${lang}`)}
							<span>{OWN_NAME[lang]}</span>
							{#if prefs.lang === lang}{@render tick()}{/if}
						</button>
					{/each}
				</div>
				<div role="group" aria-labelledby="prefs-names">
					<p id="prefs-names" class="group-label">{s.birdNames}</p>
					{#each LANGS as lang (lang)}
						<button type="button" aria-pressed={nameLang() === lang} onclick={() => setNames(lang)}>
							<span>{s.nameLangs[lang]}</span>
							{#if nameLang() === lang}{@render tick()}{/if}
						</button>
					{/each}
				</div>
			</div>
		{/if}
	</div>
</header>

{#snippet flag(lang: Lang, key: string)}
	{#if lang === 'es'}
		<svg class="flagicon" viewBox="0 0 21 12" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
			<rect width="7" height="12" fill="#006847" />
			<rect x="7" width="7" height="12" fill="#fff" />
			<rect x="14" width="7" height="12" fill="#ce1126" />
			<path d="M8.6 7.1a1.9 1.9 0 0 0 3.8 0" fill="none" stroke="#006847" stroke-width="0.45" />
			<ellipse cx="10.5" cy="5.6" rx="1.1" ry="1.3" fill="#8c5a2b" />
		</svg>
	{:else}
		<svg class="flagicon" viewBox="0 0 60 30" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
			<clipPath id="uk-{key}">
				<path d="M30 15h30v15zv15H0zH0V0zV0h30z" />
			</clipPath>
			<path d="M0 0v30h60V0z" fill="#012169" />
			<path d="M0 0l60 30m0-30L0 30" stroke="#fff" stroke-width="6" />
			<path d="M0 0l60 30m0-30L0 30" clip-path="url(#uk-{key})" stroke="#c8102e" stroke-width="4" />
			<path d="M30 0v30M0 15h60" stroke="#fff" stroke-width="10" />
			<path d="M30 0v30M0 15h60" stroke="#c8102e" stroke-width="6" />
		</svg>
	{/if}
{/snippet}

{#snippet tick()}
	<svg class="tick" viewBox="0 0 12 12" aria-hidden="true">
		<path d="M2 6.5l2.5 2.5L10 3.5" fill="none" stroke="currentColor" stroke-width="1.8" />
	</svg>
{/snippet}

{#if inQuiz}
	<nav class="upward">
		<a href="{base}/">{s.quizzes}</a>
	</nav>
{/if}

<main id="main" tabindex="-1">
	{@render children()}

	{#if installPrompt}
		<div class="installer">
			<button type="button" onclick={install}>{s.install}</button>
		</div>
	{/if}
</main>

<style>
	.bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		max-width: 46rem;
		margin: 0 auto;
		padding: 0.9rem 1rem 0;
	}

	.brand {
		display: inline-flex;
		align-items: center;
		gap: 0.6rem;
		text-decoration: none;
		font-size: 0.85rem;
		color: var(--stone);
	}
	.brand img {
		width: 40px;
		height: 40px;
	}
	.brand:hover span {
		color: var(--canopy);
		text-decoration: underline;
	}

	.prefs {
		position: relative;
	}

	.trigger {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.3rem 0.45rem;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.3rem;
		color: var(--stone);
		cursor: pointer;
		line-height: 0;
	}
	.trigger:hover,
	.trigger[aria-expanded='true'] {
		border-color: var(--canopy);
	}

	/* Not .flag: global.css already styles that class for the site's badges. */
	.flagicon {
		flex-shrink: 0;
		width: 24px;
		height: 16px;
		border-radius: 2px;
		box-shadow: 0 0 0 1px rgb(22 36 31 / 0.15);
	}

	.chevron {
		width: 10px;
		height: 6px;
	}

	.menu {
		position: absolute;
		z-index: 30;
		right: 0;
		top: calc(100% + 0.35rem);
		min-width: 11rem;
		padding: 0.35rem 0;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.4rem;
		box-shadow: 0 8px 24px rgb(22 36 31 / 0.12);
	}

	.menu [role='group'] + [role='group'] {
		margin-top: 0.35rem;
		padding-top: 0.35rem;
		border-top: 1px solid var(--rule);
	}

	.group-label {
		padding: 0.3rem 0.9rem 0.15rem;
		font-size: 0.7rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--stone);
	}

	.menu button {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: 100%;
		padding: 0.35rem 0.9rem;
		background: none;
		border: 0;
		font: inherit;
		font-size: 0.9rem;
		color: var(--ink);
		text-align: left;
		cursor: pointer;
	}
	.menu button:hover {
		background: var(--mist);
	}

	.tick {
		width: 12px;
		height: 12px;
		margin-left: auto;
		color: var(--canopy);
	}

	.upward {
		max-width: 46rem;
		margin: 0 auto;
		padding: 0.5rem 1rem 0;
	}

	.upward a {
		font-size: 0.85rem;
		color: var(--stone);
		text-decoration: none;
	}
	.upward a:hover {
		color: var(--canopy);
		text-decoration: underline;
	}

	.installer {
		max-width: 46rem;
		margin: 0 auto;
		padding: 0 1rem;
	}

	.installer button {
		display: block;
		width: 100%;
		margin-top: 1.5rem;
		padding: 0.7rem 1rem;
		background: var(--mist);
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
		font: inherit;
		font-size: 0.9rem;
		color: var(--canopy);
		cursor: pointer;
	}
	.installer button:hover {
		border-color: var(--canopy);
	}
</style>
