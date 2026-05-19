<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import {
		listActionMemories,
		getActionMemory,
		archiveActionMemory,
		getActionMemoryStats,
	} from '$lib/api/actionMemory';
	import type { ActionMemoryListItem, ActionMemory, ActionMemoryStats } from '$lib/api/actionMemory';

	let actions = $state<ActionMemoryListItem[]>([]);
	let selectedAction: ActionMemory | null = $state(null);
	let stats = $state<ActionMemoryStats | null>(null);
	let searchQuery = $state('');
	let filterType = $state('');
	let filterStatus = $state('');
	let loading = $state(true);
	let error = $state('');

	async function loadActions() {
		try {
			const result = await listActionMemories(
				1,
				100,
				searchQuery || undefined,
				filterType || undefined,
				filterStatus || undefined,
			);
			actions = result.items;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load actions';
		} finally {
			loading = false;
		}
	}

	async function loadStats() {
		try {
			stats = await getActionMemoryStats();
		} catch (e) {
			// Stats are optional, don't fail the page
		}
	}

	async function selectAction(id: number) {
		try {
			const action = await getActionMemory(id);
			selectedAction = action;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load action';
		}
	}

	async function archiveSelected() {
		if (!selectedAction) return;
		try {
			await archiveActionMemory(selectedAction.id);
			selectedAction = null;
			await loadActions();
			await loadStats();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to archive action';
		}
	}

	function formatTime(dateStr: string): string {
		const d = new Date(dateStr);
		return d.toLocaleDateString('en-GB', {
			day: '2-digit',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
		});
	}

	function formatDuration(ms: number | null): string {
		if (ms === null) return '—';
		if (ms < 1000) return `${ms}ms`;
		if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
		return `${(ms / 60000).toFixed(1)}m`;
	}

	function statusVariant(status: string): string {
		switch (status) {
			case 'success': return 'green';
			case 'failed': return 'red';
			case 'in_progress': return 'amber';
			default: return 'cyan';
		}
	}

	onMount(() => {
		loadActions();
		loadStats();
	});
</script>

<svelte:head>
	<title>BorgOS — Action Memory</title>
</svelte:head>

<div class="actions-container">
	<header class="module-header">
		<h1>ACTION MEMORY</h1>
		<p class="subtitle">Track performed actions and their outcomes</p>
	</header>

	{#if error}
		<div class="error-banner" role="alert">{error}</div>
	{:else}
		<!-- Stats Row -->
		{#if stats}
			<div class="stats-row">
				<div class="stat-card">
					<div class="stat-value">{stats.total}</div>
					<div class="stat-label">TOTAL ACTIONS</div>
				</div>
				<div class="stat-card stat-success">
					<div class="stat-value">{stats.success_count}</div>
					<div class="stat-label">SUCCESS</div>
				</div>
				<div class="stat-card stat-failed">
					<div class="stat-value">{stats.failed_count}</div>
					<div class="stat-label">FAILED</div>
				</div>
				<div class="stat-card stat-progress">
					<div class="stat-value">{stats.in_progress_count}</div>
					<div class="stat-label">IN PROGRESS</div>
				</div>
			</div>
		{/if}

		<div class="actions-layout">
			<!-- Action List Sidebar -->
			<BorgPanel class="action-list-panel">
				<div class="action-list-header">
					<BorgInput
						bind:value={searchQuery}
						placeholder="Search actions..."
						on:input={loadActions}
					/>
					<div class="filter-row">
						<select
							class="borg-select"
							value={filterType}
							oninput={(e) => { filterType = e.currentTarget.value; loadActions(); }}
						>
							<option value="">All Types</option>
							{#each stats?.action_types ?? [] as at}
								<option value={at.type}>{at.type}</option>
							{/each}
						</select>
						<select
							class="borg-select"
							value={filterStatus}
							oninput={(e) => { filterStatus = e.currentTarget.value; loadActions(); }}
						>
							<option value="">All Statuses</option>
							<option value="success">Success</option>
							<option value="failed">Failed</option>
							<option value="in_progress">In Progress</option>
						</select>
					</div>
				</div>

				{#if loading}
					<div class="loading-text">LOADING ACTIONS...</div>
				{:else}
					<ul class="action-list">
						{#each actions as action (action.id)}
							<li
								class="action-item {selectedAction?.id === action.id ? 'selected' : ''}"
								onclick={() => selectAction(action.id)}
							>
								<div class="action-item-header">
									<span class="action-title">{action.title}</span>
									<BorgBadge variant={statusVariant(action.status)} size="sm">
										{action.status.toUpperCase()}
									</BorgBadge>
								</div>
								<div class="action-item-meta">
									<span class="action-type">{action.action_type}</span>
									<span class="action-date">{formatTime(action.created_at)}</span>
								</div>
								{#if action.tools_used.length > 0}
									<div class="action-tools">
										{#each action.tools_used.slice(0, 3) as tool}
											<BorgBadge variant="cyan" size="sm">{tool}</BorgBadge>
										{/each}
										{#if action.tools_used.length > 3}
											<span class="more-tools">+{action.tools_used.length - 3}</span>
										{/if}
									</div>
								{/if}
							</li>
						{/each}
					</ul>
					{#if actions.length === 0}
						<div class="empty-state">No actions found.</div>
					{/if}
				{/if}
			</BorgPanel>

			<!-- Action Detail Panel -->
			<BorgPanel class="action-detail-panel">
				{#if selectedAction}
					<div class="detail-header">
						<h2 class="detail-title">{selectedAction.title}</h2>
						<div class="detail-actions">
							<BorgButton variant="danger" onclick={archiveSelected}>ARCHIVE</BorgButton>
						</div>
					</div>

					<div class="detail-info">
						{#if selectedAction.description}
							<div class="info-row">
								<span class="info-label">DESCRIPTION:</span>
								<span class="info-value">{selectedAction.description}</span>
							</div>
						{/if}
						<div class="info-row">
							<span class="info-label">TYPE:</span>
							<span class="info-value">{selectedAction.action_type}</span>
						</div>
						<div class="info-row">
							<span class="info-label">STATUS:</span>
							<BorgBadge variant={statusVariant(selectedAction.status)}>
								{selectedAction.status.toUpperCase()}
							</BorgBadge>
						</div>
						{#if selectedAction.tools_used.length > 0}
							<div class="info-row">
								<span class="info-label">TOOLS:</span>
								<div class="tool-list">
									{#each selectedAction.tools_used as tool}
										<BorgBadge variant="cyan" size="sm">{tool}</BorgBadge>
									{/each}
								</div>
							</div>
						{/if}
						{#if selectedAction.duration_ms !== null}
							<div class="info-row">
								<span class="info-label">DURATION:</span>
								<span class="info-value">{formatDuration(selectedAction.duration_ms)}</span>
							</div>
						{/if}
						{#if selectedAction.output_path}
							<div class="info-row">
								<span class="info-label">OUTPUT:</span>
								<code class="info-code">{selectedAction.output_path}</code>
							</div>
						{/if}
						{#if Object.keys(selectedAction.metadata).length > 0}
							<div class="info-row">
								<span class="info-label">METADATA:</span>
								<div class="metadata-grid">
									{#each Object.entries(selectedAction.metadata) as [key, value]}
										<div class="metadata-item">
											<span class="metadata-key">{key}:</span>
											<span class="metadata-value">{String(value)}</span>
										</div>
									{/each}
								</div>
							</div>
						{/if}
						{#if selectedAction.tags.length > 0}
							<div class="info-row">
								<span class="info-label">TAGS:</span>
								<div class="tag-list">
									{#each selectedAction.tags as tag}
										<BorgBadge variant="cyan" size="sm">{tag}</BorgBadge>
									{/each}
								</div>
							</div>
						{/if}
						<div class="info-row">
							<span class="info-label">CREATED:</span>
							<span class="info-value">{formatTime(selectedAction.created_at)}</span>
						</div>
						<div class="info-row">
							<span class="info-label">UPDATED:</span>
							<span class="info-value">{formatTime(selectedAction.updated_at)}</span>
						</div>
					</div>
				{:else}
					<div class="detail-empty">
						<p>Select an action to view details.</p>
						<p class="hint">Actions are automatically logged when tools or skills complete tasks.</p>
					</div>
				{/if}
			</BorgPanel>
		</div>
	{/if}
</div>

<style>
	.actions-container {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}

	.module-header h1 {
		font-size: 24px;
		color: var(--borg-cyan);
		letter-spacing: 0.15em;
		margin: 0 0 8px;
	}

	.subtitle {
		color: var(--borg-text-secondary);
		margin: 0;
		font-size: 13px;
	}

	.error-banner {
		background: var(--borg-void);
		border: 1px solid var(--borg-red);
		color: var(--borg-red);
		padding: 12px 16px;
		font-size: 13px;
	}

	.stats-row {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
	}

	.stat-card {
		background: var(--borg-void);
		border: 1px solid var(--borg-border);
		padding: 16px;
		text-align: center;
	}

	.stat-value {
		font-size: 28px;
		font-family: 'Share Tech Mono', monospace;
		color: var(--borg-cyan);
	}

	.stat-label {
		font-size: 10px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.1em;
		margin-top: 4px;
	}

	.stat-success .stat-value {
		color: var(--borg-green);
	}

	.stat-failed .stat-value {
		color: var(--borg-red);
	}

	.stat-progress .stat-value {
		color: var(--borg-amber);
	}

	.actions-layout {
		display: flex;
		gap: 16px;
		min-height: 500px;
	}

	.action-list-panel {
		width: 360px;
		min-width: 300px;
		display: flex;
		flex-direction: column;
	}

	.action-list-header {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 16px;
	}

	.filter-row {
		display: flex;
		gap: 8px;
	}

	.borg-select {
		flex: 1;
		background: var(--borg-void);
		border: 1px solid var(--borg-border);
		color: var(--borg-text-primary);
		padding: 6px 8px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		outline: none;
	}

	.borg-select:focus {
		border-color: var(--borg-cyan);
	}

	.action-list {
		list-style: none;
		padding: 0 8px;
		margin: 0;
		flex: 1;
		overflow-y: auto;
	}

	.action-item {
		padding: 12px;
		margin-bottom: 4px;
		cursor: pointer;
		border-left: 2px solid transparent;
		transition: all 150ms ease-out;
	}

	.action-item:hover {
		background: var(--borg-grid);
	}

	.action-item.selected {
		border-left-color: var(--borg-cyan);
		background: var(--borg-grid);
	}

	.action-item-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 4px;
	}

	.action-title {
		color: var(--borg-text-primary);
		font-size: 13px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.action-item-meta {
		display: flex;
		gap: 8px;
		font-size: 11px;
		color: var(--borg-text-secondary);
		margin-bottom: 4px;
	}

	.action-tools {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
	}

	.more-tools {
		color: var(--borg-text-secondary);
		font-size: 10px;
	}

	.action-detail-panel {
		flex: 1;
		display: flex;
		flex-direction: column;
	}

	.detail-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 16px;
	}

	.detail-title {
		font-size: 18px;
		color: var(--borg-cyan);
		letter-spacing: 0.1em;
		margin: 0;
	}

	.detail-actions {
		display: flex;
		gap: 8px;
	}

	.detail-info {
		padding: 0 16px 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.info-row {
		display: flex;
		gap: 12px;
		font-size: 12px;
		align-items: flex-start;
	}

	.info-label {
		color: var(--borg-text-secondary);
		min-width: 100px;
		letter-spacing: 0.05em;
	}

	.info-value {
		color: var(--borg-text-primary);
	}

	.info-code {
		color: var(--borg-green);
		font-family: 'JetBrains Mono', monospace;
		background: var(--borg-void);
		padding: 2px 6px;
		font-size: 11px;
	}

	.tool-list,
	.tag-list {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
	}

	.metadata-grid {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.metadata-item {
		display: flex;
		gap: 8px;
		font-size: 11px;
	}

	.metadata-key {
		color: var(--borg-text-secondary);
	}

	.metadata-value {
		color: var(--borg-text-primary);
	}

	.detail-empty {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		color: var(--borg-text-secondary);
		gap: 8px;
		font-size: 13px;
	}

	.hint {
		font-size: 11px;
		color: var(--borg-text-disabled);
	}

	.loading-text {
		padding: 16px;
		text-align: center;
		color: var(--borg-cyan);
		font-size: 12px;
		letter-spacing: 0.1em;
	}

	.empty-state {
		padding: 24px 16px;
		text-align: center;
		color: var(--borg-text-secondary);
		font-size: 12px;
	}
</style>
