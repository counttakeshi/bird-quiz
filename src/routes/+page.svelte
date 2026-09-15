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
		<a href="{base}/photo">
			<span class="name">Photo quiz</span>
			<span class="note">Which bird is this?</span>
		</a>
		<a href="{base}/audio">
			<span class="name">Audio quiz</span>
			<span class="note">Which bird is singing?</span>
		</a>
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

	a {
		display: block;
		padding: 1.25rem 1.25rem 1.1rem;
		background: var(--white);
		border: 1px solid var(--rule);
		border-radius: 0.35rem;
		text-decoration: none;
		color: inherit;
	}

	a:hover {
		border-color: var(--canopy);
	}

	.name {
		display: block;
		font-family: var(--display);
		font-size: 1.3rem;
		color: var(--canopy);
	}

	.note {
		display: block;
		margin-top: 0.15rem;
		font-size: 0.9rem;
		color: var(--stone);
	}

	.links {
		margin-top: 2rem;
		font-size: 0.85rem;
	}
</style>
