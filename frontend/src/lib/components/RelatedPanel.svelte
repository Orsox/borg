<script lang="ts">
	import BorgPanel from './BorgPanel.svelte';
	import { sourceColor, type BrainItemRef } from './BrainItemPanel.svelte';
	import { getItemRelations, type ItemRelations, type RelatedItem } from '$lib/api/brain';

	let {
		itemId,
		onnavigate,
	}: {
		itemId: string;
		onnavigate: (item: BrainItemRef) => void;
	} = $props();

	let relations = $state<ItemRelations | null>(null);
	let loading = $state(false);
	let error = $state('');

	$effect(() => {
		loadRelations(itemId);
	});

	async function loadRelations(id: string) {
		loading = true;
		error = '';
		try {
			const r = await getItemRelations(id);
			if (itemId !== id) return; // stale response
			relations = r;
		} catch (e) {
			if (itemId !== id) return;
			error = e instanceof Error ? e.message : 'Failed to load relations';
			relations = null;
		} finally {
			if (itemId === id) loading = false;
		}
	}

	let isEmpty = $derived(
		relations !== null &&
			relations.links.length === 0 &&
			relations.backlinks.length === 0 &&
			relations.related.length === 0,
	);

	const sections: { key: 'links' | 'backlinks' | 'related'; label: string; hint: string }[] = [
		{ key: 'links', label: 'LINKS →', hint: 'wiki-links from this item' },
		{ key: 'backlinks', label: '← BACKLINKS', hint: 'items linking here' },
		{ key: 'related', label: '# RELATED', hint: 'shared tags' },
	];
</script>

<BorgPanel class="related-panel">
	<div class="related-head">CONNECTIONS</div>

	{#if loading && !relations}
		<p class="related-status">LOADING…</p>
	{:else if error}
		<p class="related-status related-status--error">{error}</p>
	{:else if isEmpty}
		<p class="related-status">
			No connections yet. Link with [[Title]] — vault notes resolve too — or share a tag.
		</p>
	{:else if relations}
		{#each sections as section}
			{@const items = relations[section.key] as RelatedItem[]}
			{#if items.length > 0}
				<div class="related-section">
					<div class="section-label" title={section.hint}>{section.label}</div>
					<ul>
						{#each items as item (item.id)}
							<li>
								<button
									type="button"
									class="related-row"
									style:--chip={sourceColor[item.source]}
									onclick={() => onnavigate(item)}
								>
									<span class="chip-dot"></span>
									<span class="related-title">{item.title}</span>
									<span class="related-kind">{item.kind}</span>
								</button>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		{/each}
	{/if}
</BorgPanel>

<style>
	:global(.related-panel) {
		display: flex;
		flex-direction: column;
	}

	.related-head {
		padding: 12px 16px;
		border-bottom: 1px solid var(--borg-border);
		font-family: 'Share Tech Mono', monospace;
		font-size: 12px;
		letter-spacing: 0.08em;
		color: var(--borg-text-secondary);
	}

	.related-status {
		margin: 0;
		padding: 14px 16px;
		font-size: 11px;
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-text-secondary);
		line-height: 1.6;
	}

	.related-status--error {
		color: var(--borg-red);
	}

	.related-section {
		padding: 10px 0 4px;
		border-bottom: 1px solid var(--borg-border);
	}

	.related-section:last-child {
		border-bottom: none;
	}

	.section-label {
		padding: 0 16px 6px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		letter-spacing: 0.08em;
		color: var(--borg-cyan);
	}

	.related-section ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.related-row {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		padding: 6px 16px;
		cursor: pointer;
		transition: background-color 120ms ease-out;
		min-width: 0;
	}

	.related-row:hover {
		background: var(--borg-grid);
	}

	.chip-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--chip);
		flex-shrink: 0;
	}

	.related-title {
		flex: 1;
		font-size: 12px;
		color: var(--borg-text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.related-kind {
		font-size: 9px;
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		flex-shrink: 0;
	}
</style>
