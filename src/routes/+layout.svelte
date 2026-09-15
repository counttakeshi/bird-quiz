<script lang="ts">
	import '$lib/styles/global.css';
	import { asset } from '$lib/paths';
	import { base } from '$app/paths';
	import { page } from '$app/state';

	let { children } = $props();

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

<svelte:head>
	<link rel="icon" type="image/png" sizes="32x32" href={asset('favicon-32.png')} />
	<link rel="apple-touch-icon" sizes="180x180" href={asset('apple-touch-icon.png')} />
	<link rel="manifest" href={asset('quiz.webmanifest')} />
	<meta name="theme-color" content="#2f4a3c" />
	<meta name="mobile-web-app-capable" content="yes" />
	<meta name="apple-mobile-web-app-title" content="Bird Quiz" />
</svelte:head>

{#if inQuiz}
	<nav class="upward">
		<a href="{base}/">← Quizzes</a>
	</nav>
{/if}

<main id="main" tabindex="-1">
	{@render children()}

	{#if installPrompt}
		<div class="installer">
			<button type="button" onclick={install}>Install as an app</button>
		</div>
	{/if}
</main>

<style>
	.upward {
		max-width: 46rem;
		margin: 0 auto;
		padding: 1rem 1rem 0;
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
