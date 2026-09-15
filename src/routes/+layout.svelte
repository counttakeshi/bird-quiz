<script lang="ts">
	import '$lib/styles/global.css';
	import { asset } from '$lib/paths';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" type="image/png" sizes="32x32" href={asset('favicon-32.png')} />
	<link rel="apple-touch-icon" sizes="180x180" href={asset('apple-touch-icon.png')} />
</svelte:head>

<main id="main" tabindex="-1">
	{@render children()}
</main>
