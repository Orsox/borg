<script lang="ts">
	import { page } from '$app/stores';

	let { children } = $props();
</script>

{#if $page.url.pathname !== '/brain'}
	<div class="brain-breadcrumb">
		<a href="/brain">← SECOND BRAIN WORKSPACE</a>
	</div>
{/if}

{@render children()}

<style>
	.brain-breadcrumb {
		margin-bottom: 16px;
	}

	.brain-breadcrumb a {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		letter-spacing: 0.08em;
		color: var(--borg-text-secondary);
		text-decoration: none;
		border: 1px solid var(--borg-border);
		padding: 6px 12px;
		transition: all 120ms ease-out;
	}

	.brain-breadcrumb a:hover {
		color: var(--borg-cyan);
		border-color: var(--borg-cyan);
	}
</style>
