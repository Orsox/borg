<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import HexLoader from '$lib/components/HexLoader.svelte';
	import {
		getArchonSystemHealth,
		listArchonRuns,
		listArchonCodebases,
		listArchonWorkflows
	} from '$lib/api/archon-system';

	interface ArchonRun {
		id: string;
		workflow_name: string;
		status: string;
		user_message: string | null;
		started_at: string | null;
		last_activity_at: string | null;
		completed_at: string | null;
		codebase_name: string | null;
		working_path: string | null;
	}

	interface ArchonSystemHealth {
		online: boolean;
		archon_url: string;
		version: string | null;
		adapter: string | null;
		is_docker: boolean;
		active_platforms: string[];
		running_workflows: number;
		concurrency: { active: number; queued_total: number; max_concurrent: number } | null;
		checked_at: string | null;
		cached: boolean;
	}

	let loading = $state(true);
	let error = $state<string | null>(null);
	let health = $state<ArchonSystemHealth | null>(null);
	let runs = $state<ArchonRun[]>([]);
	let codebaseCount = $state(0);
	let workflowCount = $state(0);

	const archonUrl = 'http://localhost:3090';

	async function loadData() {
		loading = true;
		error = null;
		try {
			const [healthData, runsData, codebasesData, workflowsData] = await Promise.all([
				getArchonSystemHealth(),
				listArchonRuns({ limit: 5 }),
				listArchonCodebases(),
				listArchonWorkflows()
			]);
			health = healthData;
			runs = runsData.items;
			codebaseCount = codebasesData.total;
			workflowCount = workflowsData.total;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load Archon system data';
		} finally {
			loading = false;
		}
	}

	function statusBadgeStatus(status: string): 'online' | 'idle' | 'error' | 'assimilated' | 'default' {
		if (status === 'running') return 'online';
		if (status === 'completed' || status === 'success') return 'assimilated';
		if (status === 'failed' || status === 'error') return 'error';
		return 'default';
	}

	function statusBadgeLabel(status: string): string {
		return status.toUpperCase();
	}

	function truncate(str: string | null, max: number): string {
		if (!str) return '';
		return str.length > max ? str.slice(0, max) + '…' : str;
	}

	function formatTime(isoString: string | null): string {
		if (!isoString) return '—';
		try {
			return new Date(isoString).toLocaleString();
		} catch {
			return isoString;
		}
	}

	onMount(loadData);
</script>

<div class="archon-system-panel">
	<BorgPanel>
	{#if loading}
		<div class="panel-loading">
			<HexLoader size={48} />
			<p>Fetching Archon system data...</p>
		</div>
	{:else if error}
		<div class="panel-error">
			<p class="error-title">⚠ CONNECTION FAILED</p>
			<p class="error-message">{error}</p>
		</div>
	{:else if health}
		<!-- Header with status indicator -->
		<div class="panel-header">
			<h2>ARCHON SYSTEM STATUS</h2>
			<div class="header-meta">
				{#if health.cached}
					<BorgBadge status="idle">CACHED</BorgBadge>
				{/if}
				{#if health.online}
					<BorgBadge status="online">ONLINE</BorgBadge>
				{:else}
					<BorgBadge status="error">OFFLINE</BorgBadge>
				{/if}
			</div>
		</div>

		<!-- Stats grid -->
		<div class="stats-grid">
			<div class="stat-item">
				<span class="stat-label">Version</span>
				<span class="stat-value">{health.version ?? '—'}</span>
			</div>
			<div class="stat-item">
				<span class="stat-label">Running</span>
				<span class="stat-value">{health.running_workflows}</span>
			</div>
			<div class="stat-item">
				<span class="stat-label">Codebases</span>
				<span class="stat-value">{codebaseCount}</span>
			</div>
			<div class="stat-item">
				<span class="stat-label">Workflows</span>
				<span class="stat-value">{workflowCount}</span>
			</div>
		</div>

		<!-- Concurrency info -->
		{#if health.concurrency}
			<div class="concurrency-row">
				<span class="concurrency-label">Concurrency</span>
				<span class="concurrency-value">
					{health.concurrency.active} active / {health.concurrency.max_concurrent} max
					{#if health.concurrency.queued_total > 0}
						({health.concurrency.queued_total} queued)
					{/if}
				</span>
			</div>
		{/if}

		<!-- Platforms -->
		{#if health.active_platforms.length > 0}
			<div class="platforms-row">
				<span class="platforms-label">Platforms</span>
				<span class="platforms-value">{health.active_platforms.join(', ')}</span>
			</div>
		{/if}

		<!-- Recent runs -->
		{#if runs.length > 0}
			<div class="runs-section">
				<h3>RECENT RUNS</h3>
				<div class="runs-list">
					{#each runs as run (run.id)}
						<div class="run-item">
							<div class="run-info">
								<span class="run-workflow">{run.workflow_name}</span>
								<span class="run-codebase">{run.codebase_name ?? '—'}</span>
							</div>
							<div class="run-meta">
								<BorgBadge status={statusBadgeStatus(run.status)}>{statusBadgeLabel(run.status)}</BorgBadge>
								<span class="run-time">{formatTime(run.last_activity_at)}</span>
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Footer with link -->
		<div class="panel-footer">
			<a href={archonUrl} target="_blank" rel="noopener noreferrer" class="archon-link">
				Open Archon UI →
			</a>
			{#if health.checked_at}
				<span class="checked-at">Checked: {formatTime(health.checked_at)}</span>
			{/if}
		</div>
	{/if}
</BorgPanel>
</div>

<style>
	.archon-system-panel {
		margin-bottom: 24px;
	}

	.panel-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 16px;
		padding: 40px 24px;
		color: var(--borg-text-secondary);
	}

	.panel-loading p {
		font-size: 12px;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	.panel-error {
		padding: 24px;
	}

	.error-title {
		color: var(--borg-amber);
		font-size: 14px;
		margin: 0 0 8px;
		letter-spacing: 0.1em;
	}

	.error-message {
		color: var(--borg-text-secondary);
		font-size: 12px;
		margin: 0;
	}

	.panel-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 16px 24px 12px;
		border-bottom: 1px solid var(--borg-border);
	}

	.panel-header h2 {
		font-size: 14px;
		margin: 0;
		color: var(--borg-cyan);
		letter-spacing: 0.15em;
	}

	.header-meta {
		display: flex;
		gap: 8px;
		align-items: center;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 1px;
		background: var(--borg-border);
		margin: 0;
	}

	.stat-item {
		background: var(--borg-void);
		padding: 16px 24px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.stat-label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--borg-text-secondary);
	}

	.stat-value {
		font-size: 18px;
		font-weight: 700;
		color: var(--borg-text-primary);
	}

	.concurrency-row,
	.platforms-row {
		display: flex;
		gap: 12px;
		padding: 10px 24px;
		font-size: 12px;
		border-top: 1px solid var(--borg-border);
	}

	.concurrency-label,
	.platforms-label {
		color: var(--borg-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		min-width: 90px;
	}

	.concurrency-value,
	.platforms-value {
		color: var(--borg-text-primary);
	}

	.runs-section {
		padding: 16px 24px;
		border-top: 1px solid var(--borg-border);
	}

	.runs-section h3 {
		font-size: 11px;
		margin: 0 0 12px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.12em;
	}

	.runs-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.run-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 8px 12px;
		background: var(--borg-panel);
		border: 1px solid var(--borg-border);
	}

	.run-info {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.run-workflow {
		font-size: 12px;
		color: var(--borg-text-primary);
	}

	.run-codebase {
		font-size: 10px;
		color: var(--borg-text-secondary);
	}

	.run-meta {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.run-time {
		font-size: 10px;
		color: var(--borg-text-secondary);
	}

	.panel-footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 12px 24px;
		border-top: 1px solid var(--borg-border);
	}

	.archon-link {
		color: var(--borg-cyan);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		text-decoration: none;
	}

	.archon-link:hover {
		text-decoration: underline;
	}

	.checked-at {
		font-size: 10px;
		color: var(--borg-text-disabled);
	}
</style>
