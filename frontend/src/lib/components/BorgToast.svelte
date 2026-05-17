<script lang="ts">
	import { toastStore, type Toast } from '$lib/stores/toast';

	const colorMap = {
		success: 'var(--borg-green)',
		error: 'var(--borg-red)',
		warning: 'var(--borg-amber)',
		info: 'var(--borg-cyan)'
	};
</script>

<div class="toast-container" aria-live="polite">
	{#each $toastStore as toast (toast.id)}
		<div
			class="toast toast--{toast.type}"
			style="border-color: {colorMap[toast.type]}; color: {colorMap[toast.type]};"
			role="alert"
		>
			<span class="toast-message">{toast.message}</span>
			<button
				class="toast-close"
				onclick={() => toastStore.remove(toast.id)}
				aria-label="Dismiss notification"
			>✕</button>
		</div>
	{/each}
</div>

<style>
	.toast-container {
		position: fixed;
		top: 16px;
		right: 16px;
		z-index: 9999;
		display: flex;
		flex-direction: column;
		gap: 8px;
		max-width: 400px;
	}

	.toast {
		background-color: var(--borg-panel);
		border: 1px solid;
		padding: 12px 16px;
		display: flex;
		align-items: center;
		gap: 12px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 13px;
		animation: slide-in 200ms ease-out;
	}

	@keyframes slide-in {
		from { transform: translateX(100%); opacity: 0; }
		to { transform: translateX(0); opacity: 1; }
	}

	.toast-message {
		flex: 1;
	}

	.toast-close {
		background: none;
		border: none;
		cursor: pointer;
		color: inherit;
		font-size: 12px;
		padding: 0;
		opacity: 0.7;
		flex-shrink: 0;
	}

	.toast-close:hover {
		opacity: 1;
	}
</style>
