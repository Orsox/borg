<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	// Folded into the workspace: insights are now a toggleable panel on /brain.
	onMount(() => goto('/brain?insights=1', { replaceState: true }));
</script>
