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

	// ── Mini-graph: the item and its neighborhood on a radial layout ──────────
	const MINI_W = 248;
	const MINI_H = 170;
	const MINI_R = 62;
	const MINI_MAX = 10;

	let centerColor = $derived(sourceColor[itemId.split(':')[0] as keyof typeof sourceColor] ?? 'var(--borg-cyan)');

	let miniNodes = $derived.by(() => {
		if (!relations) return [];
		const neighbors = [
			...relations.links.map((item) => ({ item, dashed: false })),
			...relations.backlinks.map((item) => ({ item, dashed: false })),
			...relations.related.map((item) => ({ item, dashed: true })),
		].slice(0, MINI_MAX);
		return neighbors.map((n, i) => {
			const angle = (2 * Math.PI * i) / neighbors.length - Math.PI / 2;
			return {
				...n,
				x: MINI_W / 2 + MINI_R * Math.cos(angle),
				y: MINI_H / 2 + MINI_R * Math.sin(angle),
			};
		});
	});

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
		{#if miniNodes.length > 0}
			<div class="mini-graph-wrap">
				<svg
					class="mini-graph"
					width={MINI_W}
					height={MINI_H}
					viewBox={`0 0 ${MINI_W} ${MINI_H}`}
					role="img"
					aria-label="Connection neighborhood"
				>
					{#each miniNodes as n (n.item.id)}
						<line
							x1={MINI_W / 2}
							y1={MINI_H / 2}
							x2={n.x}
							y2={n.y}
							class="mini-edge"
							stroke-dasharray={n.dashed ? '3 3' : undefined}
						/>
					{/each}

					<circle
						cx={MINI_W / 2}
						cy={MINI_H / 2}
						r="9"
						fill="var(--borg-void)"
						stroke={centerColor}
						stroke-width="2.5"
					/>

					{#each miniNodes as n (n.item.id)}
						<g
							class="mini-node"
							role="button"
							tabindex="-1"
							onclick={() => onnavigate(n.item)}
							onkeydown={(ev) => ev.key === 'Enter' && onnavigate(n.item)}
						>
							<circle cx={n.x} cy={n.y} r="6" fill="var(--borg-void)" stroke={sourceColor[n.item.source]} stroke-width="1.5">
								<title>{n.item.title}</title>
							</circle>
							<text class="mini-label" x={n.x} y={n.y + 16} text-anchor="middle">
								{n.item.title.length > 11 ? n.item.title.slice(0, 11) + '…' : n.item.title}
							</text>
						</g>
					{/each}
				</svg>
			</div>
		{/if}

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

	.mini-graph-wrap {
		display: flex;
		justify-content: center;
		padding: 8px 0 4px;
		border-bottom: 1px solid var(--borg-border);
	}

	.mini-edge {
		stroke: var(--borg-cyan);
		stroke-width: 1;
		stroke-opacity: 0.3;
	}

	.mini-node {
		cursor: pointer;
	}

	.mini-node:hover circle {
		stroke-width: 3;
		filter: drop-shadow(0 0 5px currentColor);
	}

	.mini-label {
		font-size: 8px;
		font-family: 'JetBrains Mono', monospace;
		fill: var(--borg-text-secondary);
		pointer-events: none;
		user-select: none;
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
