<script lang="ts">
	import { page } from '$app/stores';

	let { children } = $props();

	const tabs = [
		{ href: '/brain', label: 'NOTES', icon: '◉' },
		{ href: '/brain/actions', label: 'ACTIONS', icon: '⬢' },
		{ href: '/brain/vault', label: 'VAULT', icon: '◈' },
		{ href: '/brain/graph', label: 'GRAPH', icon: '⊛' },
		{ href: '/brain/insights', label: 'INSIGHTS', icon: '◎' },
	];

	function isActive(href: string): boolean {
		const path = $page.url.pathname;
		if (href === '/brain') return path === '/brain';
		return path.startsWith(href);
	}
</script>

<div class="brain-tabs" role="tablist" aria-label="Second Brain sections">
	{#each tabs as tab}
		<a
			class="brain-tab"
			class:brain-tab--active={isActive(tab.href)}
			role="tab"
			aria-selected={isActive(tab.href)}
			href={tab.href}
		>
			<span class="brain-tab-icon" aria-hidden="true">{tab.icon}</span>
			{tab.label}
		</a>
	{/each}
</div>

{@render children()}

<style>
	.brain-tabs {
		display: flex;
		gap: 0;
		border: 1px solid var(--borg-border);
		margin-bottom: 16px;
		width: fit-content;
	}

	.brain-tab {
		display: flex;
		align-items: center;
		gap: 6px;
		background: none;
		border: none;
		border-right: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		padding: 8px 16px;
		cursor: pointer;
		letter-spacing: 0.08em;
		text-decoration: none;
		transition: all 150ms ease-out;
	}

	.brain-tab:last-child {
		border-right: none;
	}

	.brain-tab--active {
		background-color: rgba(0, 229, 255, 0.1);
		color: var(--borg-cyan);
	}

	.brain-tab:hover:not(.brain-tab--active) {
		color: var(--borg-text-primary);
		background-color: rgba(255, 255, 255, 0.04);
	}

	.brain-tab-icon {
		font-size: 12px;
	}
</style>
