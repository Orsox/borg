<script lang="ts">
	interface Props {
		status?: 'online' | 'idle' | 'error' | 'assimilated' | 'default';
		class?: string;
		children?: import('svelte').Snippet;
	}

	let { status = 'default', class: cls = '', children }: Props = $props();

	const colorMap = {
		online: 'var(--borg-green)',
		idle: 'var(--borg-amber)',
		error: 'var(--borg-red)',
		assimilated: 'var(--borg-cyan)',
		default: 'var(--borg-text-secondary)'
	};

	const color = $derived(colorMap[status] ?? colorMap.default);
</script>

<span class="borg-badge borg-badge--{status} {cls}" style="color: {color}; border-color: {color};">
	{@render children?.()}
</span>

<style>
	.borg-badge {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		font-weight: 600;
		padding: 2px 8px;
		border: 1px solid;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		display: inline-flex;
		align-items: center;
		gap: 4px;
		clip-path: polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%);
	}

	.borg-badge::before {
		content: '';
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background-color: currentColor;
		flex-shrink: 0;
	}
</style>
