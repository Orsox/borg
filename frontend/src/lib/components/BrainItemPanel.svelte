<script lang="ts" module>
	import type { GraphSource } from '$lib/api/brain';

	/** Minimal shape shared by combined-graph nodes and federated search results. */
	export interface BrainItemRef {
		id: string;
		title: string;
		source: GraphSource;
		kind: string;
		tags: string[];
		ref: string;
	}

	export const sourceColor: Record<GraphSource, string> = {
		vault: '#00e5ff',
		note: '#39ff14',
		action: '#ffaa00',
	};

	export const sourceLabel: Record<GraphSource, string> = {
		vault: 'Vault (~/Memory)',
		note: 'DB Notes',
		action: 'Action Memory',
	};
</script>

<script lang="ts">
	import BorgPanel from './BorgPanel.svelte';
	import { getNote } from '$lib/api/brain';
	import { getVaultFile } from '$lib/api/vault';
	import { getActionMemory, type ActionMemory } from '$lib/api/actionMemory';

	let { item, onclose }: { item: BrainItemRef; onclose: () => void } = $props();

	let content = $state('');
	let action = $state<ActionMemory | null>(null);
	let loading = $state(false);
	let error = $state('');

	$effect(() => {
		const current = item;
		loadItem(current);
	});

	async function loadItem(current: BrainItemRef) {
		content = '';
		action = null;
		error = '';
		loading = true;
		try {
			if (current.source === 'vault') {
				const r = await getVaultFile(current.ref);
				if (item.id !== current.id) return; // stale response
				content = r.content;
			} else if (current.source === 'note') {
				const note = await getNote(Number(current.ref));
				if (item.id !== current.id) return;
				content = note.content;
			} else {
				const a = await getActionMemory(Number(current.ref));
				if (item.id !== current.id) return;
				action = a;
			}
		} catch (e) {
			if (item.id !== current.id) return;
			error = e instanceof Error ? e.message : 'Failed to load item';
		} finally {
			if (item.id === current.id) loading = false;
		}
	}

	function formatDuration(ms: number | null): string {
		if (ms === null) return '—';
		return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
	}
</script>

<BorgPanel class="brain-item-panel">
	<div class="panel-head">
		<span class="detail-title">{item.title}</span>
		<button class="close-btn" onclick={onclose} aria-label="Close">×</button>
	</div>

	<div class="detail-meta">
		<span class="detail-badge" style:--chip={sourceColor[item.source]}>
			{sourceLabel[item.source]}
		</span>
		<span class="detail-kind">{item.kind}</span>
	</div>
	{#if item.tags.length > 0}
		<div class="detail-tags">
			{#each item.tags as tag}<span class="tag">#{tag}</span>{/each}
		</div>
	{/if}

	{#if loading}
		<p class="detail-note">Loading content…</p>
	{:else if error}
		<p class="detail-error">{error}</p>
	{:else if item.source === 'action' && action}
		<dl class="action-fields">
			<dt>STATUS</dt>
			<dd>{action.status}</dd>
			<dt>TYPE</dt>
			<dd>{action.action_type}</dd>
			{#if action.tools_used.length > 0}
				<dt>TOOLS</dt>
				<dd>{action.tools_used.join(', ')}</dd>
			{/if}
			<dt>DURATION</dt>
			<dd>{formatDuration(action.duration_ms)}</dd>
			{#if action.output_path}
				<dt>OUTPUT</dt>
				<dd class="mono">{action.output_path}</dd>
			{/if}
		</dl>
		{#if action.description}
			<pre class="detail-content">{action.description}</pre>
		{/if}
	{:else}
		<pre class="detail-content">{content}</pre>
	{/if}

	{#if item.source === 'note'}
		<a class="open-link" href={`/brain?note=${item.ref}`}>OPEN IN EDITOR →</a>
	{/if}
</BorgPanel>

<style>
	.panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
		gap: 8px;
	}

	.detail-title {
		font-size: 13px;
		color: var(--borg-text-primary);
		word-break: break-word;
	}

	.close-btn {
		background: none;
		border: none;
		color: var(--borg-text-secondary);
		font-size: 18px;
		cursor: pointer;
		line-height: 1;
	}

	.close-btn:hover {
		color: var(--borg-red);
	}

	.detail-meta {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 10px;
	}

	.detail-badge {
		font-size: 10px;
		font-family: 'JetBrains Mono', monospace;
		color: var(--chip);
		border: 1px solid var(--chip);
		padding: 2px 8px;
	}

	.detail-kind {
		font-size: 10px;
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.detail-tags {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		margin-bottom: 12px;
	}

	.tag {
		font-size: 10px;
		color: var(--borg-cyan);
		font-family: 'JetBrains Mono', monospace;
		opacity: 0.8;
	}

	.detail-note {
		color: var(--borg-text-secondary);
		font-size: 12px;
		font-style: italic;
	}

	.detail-error {
		color: var(--borg-red);
		font-size: 12px;
	}

	.action-fields {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 6px 14px;
		margin: 0 0 12px;
		font-size: 12px;
	}

	.action-fields dt {
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		letter-spacing: 0.05em;
	}

	.action-fields dd {
		margin: 0;
		color: var(--borg-text-primary);
	}

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		word-break: break-all;
	}

	.detail-content {
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		color: var(--borg-text-primary);
		white-space: pre-wrap;
		word-break: break-word;
		line-height: 1.6;
		margin: 0;
		max-height: 560px;
		overflow-y: auto;
	}

	.open-link {
		display: inline-block;
		margin-top: 12px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		letter-spacing: 0.05em;
		color: var(--borg-green, #39ff14);
		text-decoration: none;
		border: 1px solid var(--borg-border);
		padding: 5px 10px;
		transition: all 120ms ease-out;
	}

	.open-link:hover {
		border-color: var(--borg-green, #39ff14);
	}
</style>
