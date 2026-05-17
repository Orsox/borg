<script lang="ts">
	let { class: cls = '', children } = $props();
</script>

<div class="borg-panel {cls}">
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
</style>
