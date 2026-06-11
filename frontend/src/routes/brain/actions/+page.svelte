<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	// Folded into the workspace: actions are now a source filter on /brain.
	onMount(() => goto('/brain?sources=action', { replaceState: true }));
</script>
