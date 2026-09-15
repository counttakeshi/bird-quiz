<script lang="ts">
	import { base } from '$app/paths';
	import { dev } from '$app/environment';

	// Nothing heavy is imported here on purpose. The two quizzes carry a
	// megabyte of harvested data between them, and SvelteKit splits per route,
	// so this page loads neither until you pick one.
</script>

<svelte:head>
	<title>Bird ID quiz</title>
	<meta name="description" content="Compare confusion species side by side." />
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="wrap">
	<h1>Bird ID quiz</h1>

	<nav>
		<a href="{base}/photo">Photo quiz</a>
		<a href="{base}/audio">Audio quiz</a>
	</nav>

	{#if dev}
		<p class="links"><a href="{base}/edit">Edit the notes and photographs</a></p>
	{/if}
</div>

<style>
	.wrap {
		max-width: 46rem;
		margin: 0 auto;
		padding: 2.5rem 1rem 3rem;
	}

	h1 {
		margin: 0 0 1.5rem;
	}

	nav {
		display: grid;
		gap: 0.75rem;
	}

	@media (min-width: 30rem) {
		nav {
			grid-template-columns: 1fr 1fr;
		}
	}

	nav a {
		display: block;
		padding: 1.25rem;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
		text-decoration: none;
		font-family: var(--display);
		font-size: 1.3rem;
		color: var(--canopy);
	}

	nav a:hover {
		border-color: var(--canopy);
	}

	.links {
		margin-top: 2rem;
		font-size: 0.85rem;
	}
</style>
