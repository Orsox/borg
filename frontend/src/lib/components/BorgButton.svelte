<script lang="ts">
	interface Props {
		variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
		disabled?: boolean;
		type?: 'button' | 'submit' | 'reset';
		class?: string;
		onclick?: (e: MouseEvent) => void;
		children?: import('svelte').Snippet;
	}

	let {
		variant = 'primary',
		disabled = false,
		type = 'button',
		class: cls = '',
		onclick,
		children
	}: Props = $props();
</script>

<button
	{type}
	{disabled}
	class="borg-btn borg-btn--{variant} {cls}"
	{onclick}
>
	{@render children?.()}
</button>

<style>
	.borg-btn {
		font-family: 'JetBrains Mono', monospace;
		font-size: 13px;
		padding: 8px 16px;
		border-radius: 0;
		border: 1px solid transparent;
		cursor: pointer;
		transition: all 150ms ease-out;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}

	.borg-btn:disabled {
		opacity: 0.3;
		cursor: not-allowed;
	}

	/* Primary - cyan fill */
	.borg-btn--primary {
		background-color: var(--borg-cyan);
		color: var(--borg-black);
		border-color: var(--borg-cyan);
	}
	.borg-btn--primary:hover:not(:disabled) {
		background-color: var(--borg-cyan-dim);
		border-color: var(--borg-cyan-dim);
	}
	.borg-btn--primary:active:not(:disabled) {
		box-shadow: var(--glow-cyan), inset 0 1px 3px rgba(0, 0, 0, 0.3);
	}

	/* Secondary - transparent + cyan border */
	.borg-btn--secondary {
		background-color: transparent;
		color: var(--borg-cyan);
		border-color: var(--borg-cyan);
	}
	.borg-btn--secondary:hover:not(:disabled) {
		background-color: rgba(0, 229, 255, 0.08);
		border-color: var(--borg-cyan-dim);
	}
	.borg-btn--secondary:active:not(:disabled) {
		box-shadow: var(--glow-cyan);
	}

	/* Danger - red border */
	.borg-btn--danger {
		background-color: transparent;
		color: var(--borg-red);
		border-color: var(--borg-red);
	}
	.borg-btn--danger:hover:not(:disabled) {
		background-color: rgba(255, 34, 68, 0.08);
	}
	.borg-btn--danger:active:not(:disabled) {
		box-shadow: var(--glow-red);
	}

	/* Ghost - no border */
	.borg-btn--ghost {
		background-color: transparent;
		color: var(--borg-text-secondary);
		border-color: transparent;
	}
	.borg-btn--ghost:hover:not(:disabled) {
		color: var(--borg-text-primary);
		background-color: rgba(255, 255, 255, 0.04);
	}
</style>
