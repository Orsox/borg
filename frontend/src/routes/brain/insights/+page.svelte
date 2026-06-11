<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import HexLoader from '$lib/components/HexLoader.svelte';
	import { toastStore } from '$lib/stores/toast';
	import {
		listInsights,
		acknowledgeInsight,
		resolveInsight,
		generateInsights,
	} from '$lib/api/insights';
	import type { Insight } from '$lib/api/insights';

	const statusFilters = ['open', 'acknowledged', 'resolved', 'all'];

	let insights = $state<Insight[]>([]);
	let activeStatus = $state('open');
	let loading = $state(true);
	let generating = $state(false);
	let error = $state('');

	async function loadInsights() {
		loading = true;
		try {
			const result = await listInsights(activeStatus, 1, 100);
			insights = result.items;
			error = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load insights';
		} finally {
			loading = false;
		}
	}

	async function setFilter(status: string) {
		activeStatus = status;
		await loadInsights();
	}

	async function acknowledge(id: number) {
		try {
			await acknowledgeInsight(id);
			await loadInsights();
		} catch (e) {
			toastStore.error(e instanceof Error ? e.message : 'Failed to acknowledge');
		}
	}

	async function resolve(id: number) {
		try {
			await resolveInsight(id);
			await loadInsights();
		} catch (e) {
			toastStore.error(e instanceof Error ? e.message : 'Failed to resolve');
		}
	}

	async function regenerate() {
		generating = true;
		try {
			const result = await generateInsights(14);
			toastStore.success(
				`Insights regenerated: ${result.created} new, ${result.updated} updated, ${result.total_open} open`,
			);
			await loadInsights();
		} catch (e) {
			toastStore.error(e instanceof Error ? e.message : 'Failed to regenerate');
		} finally {
			generating = false;
		}
	}

	function badgeStatus(status: string): 'error' | 'idle' | 'online' {
		if (status === 'open') return 'error';
		if (status === 'acknowledged') return 'idle';
		return 'online';
	}

	function formatTime(dateStr: string | null): string {
		if (!dateStr) return '—';
		return new Date(dateStr).toLocaleDateString('en-GB', {
			day: '2-digit',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
		});
	}

	onMount(loadInsights);
</script>

<svelte:head>
	<title>BorgOS — Insights</title>
</svelte:head>

<div class="insights-page">
	<header class="page-header">
		<div>
			<h1>INSIGHTS</h1>
			<p class="subtitle">Lessons from failed runs — what the collective must improve</p>
		</div>
		<BorgButton variant="secondary" disabled={generating} onclick={regenerate}>
			{generating ? '… GENERATING' : '↺ REGENERATE'}
		</BorgButton>
	</header>

	<div class="filter-tabs" role="tablist" aria-label="Insight status filter">
		{#each statusFilters as status}
			<button
				class="filter-tab"
				class:filter-tab--active={activeStatus === status}
				role="tab"
				aria-selected={activeStatus === status}
				onclick={() => setFilter(status)}
			>
				{status.toUpperCase()}
			</button>
		{/each}
	</div>

	{#if loading}
		<div class="center-state"><HexLoader /></div>
	{:else if error}
		<p class="error-text">{error}</p>
	{:else if insights.length === 0}
		<p class="empty-state">No {activeStatus === 'all' ? '' : activeStatus + ' '}insights — the collective is performing adequately.</p>
	{:else}
		<div class="insight-list">
			{#each insights as insight (insight.id)}
				<BorgPanel class="insight-card">
					<div class="insight-inner">
						<div class="insight-head">
							<BorgBadge status={badgeStatus(insight.status)}>{insight.status}</BorgBadge>
							<span class="insight-category">{insight.category}</span>
							{#if insight.workflow}
								<span class="insight-workflow">@ {insight.workflow}</span>
							{/if}
							<span class="insight-count">{insight.occurrences}×</span>
						</div>
						<p class="insight-summary">{insight.summary}</p>
						<p class="insight-recommendation">▶ {insight.recommendation}</p>
						<div class="insight-meta">
							<span>First seen: {formatTime(insight.first_seen)}</span>
							<span>Last seen: {formatTime(insight.last_seen)}</span>
							<a href="/brain/actions">{insight.evidence_action_ids.length} linked action(s)</a>
						</div>
						{#if insight.status !== 'resolved'}
							<div class="insight-actions">
								{#if insight.status === 'open'}
									<BorgButton variant="ghost" onclick={() => acknowledge(insight.id)}>
										ACKNOWLEDGE
									</BorgButton>
								{/if}
								<BorgButton variant="secondary" onclick={() => resolve(insight.id)}>
									RESOLVE
								</BorgButton>
							</div>
						{/if}
					</div>
				</BorgPanel>
			{/each}
		</div>
	{/if}
</div>

<style>
	.insights-page {
		max-width: 900px;
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 24px;
	}

	.page-header h1 {
		font-size: 24px;
		color: var(--borg-cyan);
		margin: 0 0 4px;
		letter-spacing: 0.15em;
	}

	.subtitle {
		color: var(--borg-text-secondary);
		font-size: 13px;
		margin: 0;
	}

	.filter-tabs {
		display: flex;
		gap: 0;
		border: 1px solid var(--borg-border);
		margin-bottom: 16px;
		width: fit-content;
	}

	.filter-tab {
		background: none;
		border: none;
		border-right: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		padding: 8px 16px;
		cursor: pointer;
		letter-spacing: 0.08em;
		transition: all 150ms ease-out;
	}

	.filter-tab:last-child {
		border-right: none;
	}

	.filter-tab--active {
		background-color: rgba(0, 229, 255, 0.1);
		color: var(--borg-cyan);
	}

	.filter-tab:hover:not(.filter-tab--active) {
		color: var(--borg-text-primary);
		background-color: rgba(255, 255, 255, 0.04);
	}

	.center-state {
		display: flex;
		justify-content: center;
		padding: 48px;
	}

	.error-text {
		color: var(--borg-red);
		font-size: 13px;
	}

	.empty-state {
		color: var(--borg-text-secondary);
		font-size: 13px;
		padding: 24px 0;
	}

	.insight-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.insight-inner {
		padding: 16px;
	}

	.insight-head {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 12px;
	}

	.insight-category {
		font-family: 'Share Tech Mono', monospace;
		font-size: 14px;
		color: var(--borg-cyan);
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	.insight-workflow {
		color: var(--borg-text-secondary);
		font-size: 13px;
	}

	.insight-count {
		margin-left: auto;
		font-family: 'JetBrains Mono', monospace;
		font-size: 14px;
		color: var(--borg-amber);
	}

	.insight-summary {
		color: var(--borg-text-primary);
		font-size: 13px;
		margin: 0 0 8px;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.insight-recommendation {
		color: var(--borg-green);
		font-size: 13px;
		margin: 0 0 12px;
		padding: 8px 12px;
		border-left: 2px solid var(--borg-green);
		background-color: rgba(0, 255, 128, 0.05);
	}

	.insight-meta {
		display: flex;
		gap: 16px;
		font-size: 11px;
		color: var(--borg-text-secondary);
		margin-bottom: 12px;
		flex-wrap: wrap;
	}

	.insight-meta a {
		color: var(--borg-cyan);
		text-decoration: none;
	}

	.insight-meta a:hover {
		text-decoration: underline;
	}

	.insight-actions {
		display: flex;
		gap: 8px;
	}
</style>
