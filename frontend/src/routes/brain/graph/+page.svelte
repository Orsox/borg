<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	// Folded into the workspace: the graph is now a view toggle on /brain.
	onMount(() => goto('/brain?view=graph', { replaceState: true }));
</script>
