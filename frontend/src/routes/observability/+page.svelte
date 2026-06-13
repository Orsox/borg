<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import BorgTable from '$lib/components/BorgTable.svelte';
	import HexLoader from '$lib/components/HexLoader.svelte';
	import {
		getObservabilityStatus, listTraces, getTrace,
	} from '$lib/api/observability';
	import type {
		ObservabilityStatus, TraceSummary, TraceDetail,
	} from '$lib/api/observability';

	const SURFACE_TAGS = [
		{ tag: '', label: 'ALL' },
		{ tag: 'agent-mode', label: 'AGENT MODE' },
		{ tag: 'persona-chat', label: 'PERSONA CHAT' },
		{ tag: 'dreaming', label: 'DREAMING' },
		{ tag: 'skill-execution', label: 'SKILLS' },
	];

	let status = $state<ObservabilityStatus | null>(null);
	let traces = $state<TraceSummary[]>([]);
	let selectedTrace = $state<TraceDetail | null>(null);
	let loading = $state(true);
	let tracesLoading = $state(false);
	let detailLoading = $state(false);
	let error = $state('');

	let activeTag = $state('');
	let activePersona = $state('');
	let page = $state(1);
	let pages = $state(0);
	let total = $state(0);

	const online = $derived(status?.configured && status?.reachable);

	function formatTime(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString('de-DE', {
			timeZone: 'Europe/Berlin',
			day: '2-digit', month: '2-digit',
			hour: '2-digit', minute: '2-digit', second: '2-digit',
		});
	}

	function formatLatency(ms: number | null): string {
		if (ms === null || ms === undefined) return '—';
		if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
		return `${Math.round(ms)}ms`;
	}

	function levelStatus(level: string | null): 'online' | 'idle' | 'error' | 'default' {
		if (level === 'ERROR') return 'error';
		if (level === 'WARNING') return 'idle';
		if (level === 'DEFAULT') return 'online';
		return 'default';
	}

	function pretty(value: unknown): string {
		if (value === null || value === undefined) return '—';
		if (typeof value === 'string') return value;
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	}

	function usageLabel(usage: Record<string, number>): string {
		const parts: string[] = [];
		if (usage.input !== undefined) parts.push(`in ${usage.input}`);
		if (usage.output !== undefined) parts.push(`out ${usage.output}`);
		if (usage.total !== undefined) parts.push(`Σ ${usage.total}`);
		return parts.join(' · ');
	}

	async function loadStatus() {
		try {
			status = await getObservabilityStatus();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load Langfuse status';
		}
	}

	async function loadTraces() {
		if (!online) return;
		tracesLoading = true;
		error = '';
		try {
			const result = await listTraces({
				page,
				size: 25,
				tag: activeTag || undefined,
				persona: activePersona || undefined,
			});
			traces = result.items;
			pages = result.pages;
			total = result.total;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load traces';
		} finally {
			tracesLoading = false;
		}
	}

	async function selectTrace(id: string) {
		detailLoading = true;
		try {
			selectedTrace = await getTrace(id);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load trace';
		} finally {
			detailLoading = false;
		}
	}

	function setTag(tag: string) {
		activeTag = tag;
		page = 1;
		loadTraces();
	}

	function setPersona(persona: string) {
		activePersona = activePersona === persona ? '' : persona;
		page = 1;
		loadTraces();
	}

	function gotoPage(p: number) {
		page = p;
		loadTraces();
	}

	async function refresh() {
		await loadStatus();
		await loadTraces();
	}

	onMount(async () => {
		await loadStatus();
		if (online) await loadTraces();
		loading = false;
	});
</script>

<svelte:head>
	<title>BorgOS — Observability</title>
</svelte:head>

<div class="obs-container">
	<header class="module-header">
		<div class="header-row">
			<div>
				<h1>OBSERVABILITY</h1>
				<p class="subtitle">Agent work traces — Langfuse</p>
			</div>
			<div class="header-actions">
				{#if status}
					{#if !status.configured}
						<BorgBadge status="idle">NOT CONFIGURED</BorgBadge>
					{:else if status.reachable}
						<BorgBadge status="online">LANGFUSE ONLINE</BorgBadge>
					{:else}
						<BorgBadge status="error">UNREACHABLE</BorgBadge>
					{/if}
					{#if !status.tracing_enabled && status.configured}
						<BorgBadge status="idle">INGESTION OFF</BorgBadge>
					{/if}
				{/if}
				{#if status?.ui_url}
					<a class="ext-link" href={status.ui_url} target="_blank" rel="noopener noreferrer">
						OPEN LANGFUSE UI ↗
					</a>
				{/if}
				<BorgButton variant="secondary" onclick={refresh} disabled={tracesLoading}>
					{tracesLoading ? 'SYNCING…' : 'REFRESH'}
				</BorgButton>
			</div>
		</div>
	</header>

	{#if loading}
		<div class="center-state"><HexLoader /></div>
	{:else if !status?.configured}
		<BorgPanel>
			{#snippet header()}LANGFUSE NOT CONFIGURED{/snippet}
			<div class="setup-hint">
				<p>The collective has no tracing uplink. To assimilate agent telemetry:</p>
				<ol>
					<li>Start the stack: <code>make observability-up</code> (config: <code>observability/.env</code>)</li>
					<li>Set in <code>backend/.env</code>: <code>LANGFUSE_ENABLED=true</code>, <code>LANGFUSE_PUBLIC_KEY</code>, <code>LANGFUSE_SECRET_KEY</code>, <code>LANGFUSE_UI_URL</code></li>
					<li>Restart the backend</li>
				</ol>
			</div>
		</BorgPanel>
	{:else if !status.reachable}
		<BorgPanel>
			{#snippet header()}LANGFUSE UNREACHABLE{/snippet}
			<div class="setup-hint">
				<p>Configured host <code>{status.host}</code> is not responding{status.error ? ` — ${status.error}` : ''}.</p>
				<p>Check the stack: <code>docker compose -f observability/docker-compose.yml ps</code></p>
			</div>
		</BorgPanel>
	{:else}
		{#if error}
			<div class="error-banner" role="alert">{error}</div>
		{/if}

		<div class="filter-bar">
			<div class="filter-group" role="group" aria-label="Surface filter">
				{#each SURFACE_TAGS as s}
					<button
						class="filter-chip"
						class:filter-chip--active={activeTag === s.tag}
						onclick={() => setTag(s.tag)}
					>{s.label}</button>
				{/each}
			</div>
			<div class="filter-group" role="group" aria-label="Persona filter">
				{#each ['locutus', 'seven'] as p}
					<button
						class="filter-chip filter-chip--persona"
						class:filter-chip--active={activePersona === p}
						onclick={() => setPersona(p)}
					>{p.toUpperCase()}</button>
				{/each}
			</div>
			<span class="trace-count">{total} TRACES</span>
		</div>

		<div class="obs-layout" class:obs-layout--split={selectedTrace !== null}>
			<BorgPanel class="traces-panel">
				{#snippet header()}TRACES{/snippet}
				{#if tracesLoading && traces.length === 0}
					<div class="center-state"><HexLoader size={32} /></div>
				{:else if traces.length === 0}
					<div class="empty-state">No traces in this segment of the collective.</div>
				{:else}
					<BorgTable headers={['Time', 'Name', 'Persona', 'Latency', 'Level', 'Session']}>
						{#each traces as trace (trace.id)}
							<tr
								class="trace-row"
								class:trace-row--selected={selectedTrace?.id === trace.id}
								onclick={() => selectTrace(trace.id)}
							>
								<td class="cell-time">{formatTime(trace.timestamp)}</td>
								<td class="cell-name" title={trace.input_preview ?? ''}>{trace.name ?? '—'}</td>
								<td>
									{#if trace.persona}
										<BorgBadge status={trace.persona === 'seven' ? 'assimilated' : 'online'}>
											{trace.persona}
										</BorgBadge>
									{:else}—{/if}
								</td>
								<td class="cell-latency">{formatLatency(trace.latency_ms)}</td>
								<td><BorgBadge status={levelStatus(trace.level)}>{trace.level ?? 'n/a'}</BorgBadge></td>
								<td class="cell-session">{trace.session_id ?? '—'}</td>
							</tr>
						{/each}
					</BorgTable>
					{#if pages > 1}
						<div class="pagination">
							<BorgButton variant="ghost" disabled={page <= 1} onclick={() => gotoPage(page - 1)}>‹ PREV</BorgButton>
							<span class="page-indicator">{page} / {pages}</span>
							<BorgButton variant="ghost" disabled={page >= pages} onclick={() => gotoPage(page + 1)}>NEXT ›</BorgButton>
						</div>
					{/if}
				{/if}
			</BorgPanel>

			{#if selectedTrace}
				<BorgPanel class="detail-panel">
					{#snippet header()}TRACE DETAIL{/snippet}
					{#if detailLoading}
						<div class="center-state"><HexLoader size={32} /></div>
					{:else}
						<div class="detail-body">
							<div class="detail-head">
								<span class="detail-name">{selectedTrace.name ?? selectedTrace.id}</span>
								<div class="detail-head-actions">
									{#if selectedTrace.ui_url}
										<a class="ext-link" href={selectedTrace.ui_url} target="_blank" rel="noopener noreferrer">LANGFUSE ↗</a>
									{/if}
									<button class="detail-close" onclick={() => (selectedTrace = null)} aria-label="Close detail">✕</button>
								</div>
							</div>
							<dl class="detail-meta">
								<dt>Time</dt><dd>{formatTime(selectedTrace.timestamp)}</dd>
								<dt>Persona</dt><dd>{selectedTrace.persona ?? '—'}</dd>
								<dt>Session</dt><dd>{selectedTrace.session_id ?? '—'}</dd>
								<dt>Latency</dt><dd>{formatLatency(selectedTrace.latency_ms)}</dd>
								<dt>Tags</dt><dd>{selectedTrace.tags.join(', ') || '—'}</dd>
							</dl>

							{#if selectedTrace.input !== null && selectedTrace.input !== undefined}
								<div class="io-block">
									<span class="io-label">INPUT</span>
									<pre class="io-content">{pretty(selectedTrace.input)}</pre>
								</div>
							{/if}
							{#if selectedTrace.output !== null && selectedTrace.output !== undefined}
								<div class="io-block">
									<span class="io-label">OUTPUT</span>
									<pre class="io-content">{pretty(selectedTrace.output)}</pre>
								</div>
							{/if}

							{#if selectedTrace.observations.length > 0}
								<span class="io-label">OBSERVATIONS ({selectedTrace.observations.length})</span>
								<div class="obs-list">
									{#each selectedTrace.observations as obs (obs.id)}
										<div class="obs-item" class:obs-item--error={obs.level === 'ERROR'}>
											<div class="obs-item-head">
												<span class="obs-type" class:obs-type--gen={obs.type === 'GENERATION'}>
													{obs.type === 'GENERATION' ? '◈ GEN' : '▸ SPAN'}
												</span>
												<span class="obs-name">{obs.name ?? obs.id}</span>
												{#if obs.model}<span class="obs-model">{obs.model}</span>{/if}
												{#if usageLabel(obs.usage)}<span class="obs-usage">{usageLabel(obs.usage)}</span>{/if}
											</div>
											{#if obs.status_message}
												<div class="obs-status-msg">{obs.status_message}</div>
											{/if}
											{#if obs.output !== null && obs.output !== undefined}
												<pre class="io-content io-content--small">{pretty(obs.output)}</pre>
											{/if}
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</BorgPanel>
			{/if}
		</div>
	{/if}
</div>

<style>
	.obs-container {
		padding: 24px;
		max-width: 1600px;
	}

	.module-header {
		margin-bottom: 24px;
	}

	.header-row {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 16px;
		flex-wrap: wrap;
	}

	.module-header h1 {
		font-family: 'Share Tech Mono', monospace;
		font-size: 24px;
		color: var(--borg-cyan);
		letter-spacing: 0.15em;
		margin: 0;
	}

	.subtitle {
		color: var(--borg-text-secondary);
		font-size: 13px;
		margin: 4px 0 0;
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
	}

	.ext-link {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		color: var(--borg-cyan);
		text-decoration: none;
		border: 1px solid var(--borg-border);
		padding: 6px 12px;
		letter-spacing: 0.05em;
		transition: all 150ms ease-out;
	}

	.ext-link:hover {
		border-color: var(--borg-cyan);
		background-color: rgba(0, 229, 255, 0.06);
	}

	.center-state {
		display: flex;
		justify-content: center;
		padding: 48px;
	}

	.empty-state {
		padding: 32px;
		text-align: center;
		color: var(--borg-text-secondary);
		font-size: 13px;
	}

	.error-banner {
		border: 1px solid var(--borg-red);
		color: var(--borg-red);
		padding: 12px 16px;
		font-size: 13px;
		margin-bottom: 16px;
	}

	.setup-hint {
		padding: 16px;
		color: var(--borg-text-secondary);
		font-size: 13px;
		line-height: 1.7;
	}

	.setup-hint code {
		color: var(--borg-cyan);
		background-color: var(--borg-grid);
		padding: 1px 6px;
	}

	.filter-bar {
		display: flex;
		align-items: center;
		gap: 16px;
		margin-bottom: 16px;
		flex-wrap: wrap;
	}

	.filter-group {
		display: flex;
		gap: 4px;
	}

	.filter-chip {
		background: none;
		border: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		padding: 6px 12px;
		cursor: pointer;
		letter-spacing: 0.05em;
		transition: all 150ms ease-out;
	}

	.filter-chip:hover {
		color: var(--borg-text-primary);
		border-color: var(--borg-border-active);
	}

	.filter-chip--active {
		color: var(--borg-cyan);
		border-color: var(--borg-cyan);
		background-color: rgba(0, 229, 255, 0.06);
	}

	.filter-chip--persona.filter-chip--active {
		color: var(--borg-green);
		border-color: var(--borg-green);
		background-color: rgba(0, 255, 136, 0.06);
	}

	.trace-count {
		margin-left: auto;
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.08em;
	}

	.obs-layout {
		display: grid;
		grid-template-columns: 1fr;
		gap: 16px;
	}

	.obs-layout--split {
		grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
	}

	@media (max-width: 1100px) {
		.obs-layout--split {
			grid-template-columns: 1fr;
		}
	}

	.trace-row {
		cursor: pointer;
	}

	:global(.trace-row--selected td) {
		background-color: rgba(0, 229, 255, 0.08);
	}

	.cell-time, .cell-latency, .cell-session {
		white-space: nowrap;
		font-size: 12px;
		color: var(--borg-text-secondary);
	}

	.cell-name {
		color: var(--borg-text-primary);
	}

	.cell-session {
		max-width: 180px;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 16px;
		padding: 12px;
	}

	.page-indicator {
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		color: var(--borg-text-secondary);
	}

	.detail-body {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 16px;
		max-height: 75vh;
		overflow-y: auto;
	}

	.detail-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}

	.detail-head-actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.detail-name {
		font-family: 'Share Tech Mono', monospace;
		font-size: 15px;
		color: var(--borg-cyan);
		letter-spacing: 0.05em;
		word-break: break-all;
	}

	.detail-close {
		background: none;
		border: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		font-size: 12px;
		width: 28px;
		height: 28px;
		cursor: pointer;
		transition: all 150ms ease-out;
	}

	.detail-close:hover {
		border-color: var(--borg-red);
		color: var(--borg-red);
	}

	.detail-meta {
		display: grid;
		grid-template-columns: 80px 1fr;
		gap: 6px 12px;
		margin: 0;
		font-size: 12px;
	}

	.detail-meta dt {
		color: var(--borg-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-size: 11px;
	}

	.detail-meta dd {
		margin: 0;
		color: var(--borg-text-primary);
		font-family: 'JetBrains Mono', monospace;
		word-break: break-all;
	}

	.io-block {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.io-label {
		font-family: 'Share Tech Mono', monospace;
		font-size: 11px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.1em;
	}

	.io-content {
		background-color: var(--borg-grid);
		border: 1px solid var(--borg-border);
		border-left: 3px solid var(--borg-cyan);
		padding: 10px 12px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		color: var(--borg-text-primary);
		white-space: pre-wrap;
		word-break: break-word;
		margin: 0;
		max-height: 240px;
		overflow-y: auto;
	}

	.io-content--small {
		font-size: 11px;
		max-height: 140px;
		border-left-color: var(--borg-border-active);
	}

	.obs-list {
		display: flex;
		flex-direction: column;
		gap: 10px;
		margin-top: 6px;
	}

	.obs-item {
		border: 1px solid var(--borg-border);
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.obs-item--error {
		border-color: var(--borg-red);
	}

	.obs-item-head {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
		font-size: 12px;
	}

	.obs-type {
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.08em;
	}

	.obs-type--gen {
		color: var(--borg-cyan);
	}

	.obs-name {
		color: var(--borg-text-primary);
		font-family: 'JetBrains Mono', monospace;
	}

	.obs-model {
		color: var(--borg-green);
		font-size: 11px;
		font-family: 'JetBrains Mono', monospace;
	}

	.obs-usage {
		margin-left: auto;
		color: var(--borg-text-secondary);
		font-size: 11px;
		font-family: 'JetBrains Mono', monospace;
	}

	.obs-status-msg {
		color: var(--borg-red);
		font-size: 12px;
		font-family: 'JetBrains Mono', monospace;
	}
</style>
