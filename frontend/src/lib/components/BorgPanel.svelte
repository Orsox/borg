<script lang="ts">
	let { class: cls = '', header = undefined, children } = $props();
</script>

<div class="borg-panel {cls}">
	{#if header}
		<div class="borg-panel-header">{@render header()}</div>
	{/if}
	{@render children?.()}
</div>

<style>
	.borg-panel {
		background-color: var(--borg-void);
		border: 1px solid var(--borg-border);
		border-radius: 0;
		box-shadow: inset 0 1px 0 0 rgba(0, 229, 255, 0.05);
		position: relative;
	}

	.borg-panel-header {
		padding: 12px 16px;
		border-bottom: 1px solid var(--borg-border);
		font-family: 'Share Tech Mono', monospace;
		font-size: 12px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--borg-text-secondary);
	}
</style>
