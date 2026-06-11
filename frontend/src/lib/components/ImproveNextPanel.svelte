<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import { getTopInsights } from '$lib/api/insights';
	import type { Insight } from '$lib/api/insights';

	let insights = $state<Insight[]>([]);
	let loaded = $state(false);

	onMount(async () => {
		try {
			insights = await getTopInsights(3);
		} catch {
			// Panel is optional — never break the dashboard.
		} finally {
			loaded = true;
		}
	});
</script>

{#if loaded}
	<BorgPanel class="improve-next-panel">
		{#snippet header()}IMPROVE NEXT{/snippet}
		<div class="improve-inner">
			{#if insights.length === 0}
				<p class="all-clear">No open improvement reminders. Resistance was futile.</p>
			{:else}
				{#each insights as insight (insight.id)}
					<div class="improve-row">
						<span class="improve-count">{insight.occurrences}×</span>
						<span class="improve-label">
							{insight.category}{insight.workflow ? ` @ ${insight.workflow}` : ''}
						</span>
						<span class="improve-rec">{insight.recommendation}</span>
					</div>
				{/each}
				<a href="/brain/insights" class="improve-link">All insights →</a>
			{/if}
		</div>
	</BorgPanel>
{/if}

<style>
	:global(.improve-next-panel) {
		margin-bottom: 16px;
	}

	.improve-inner {
		padding: 12px 16px;
	}

	.all-clear {
		color: var(--borg-text-secondary);
		font-size: 12px;
		margin: 0;
	}

	.improve-row {
		display: flex;
		align-items: baseline;
		gap: 12px;
		padding: 6px 0;
		border-bottom: 1px solid var(--borg-border);
		font-size: 12px;
	}

	.improve-row:last-of-type {
		border-bottom: none;
	}

	.improve-count {
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-amber);
		flex-shrink: 0;
		min-width: 28px;
	}

	.improve-label {
		font-family: 'Share Tech Mono', monospace;
		color: var(--borg-cyan);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		flex-shrink: 0;
	}

	.improve-rec {
		color: var(--borg-text-secondary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.improve-link {
		display: inline-block;
		margin-top: 8px;
		color: var(--borg-cyan);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		text-decoration: none;
	}

	.improve-link:hover {
		text-decoration: underline;
	}
</style>
