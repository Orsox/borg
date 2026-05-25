<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		forceSimulation,
		forceManyBody,
		forceLink,
		forceCenter,
		forceCollide,
		type Simulation,
	} from 'd3-force';
	import { select } from 'd3-selection';
	import { zoom as d3Zoom, zoomIdentity, type ZoomBehavior } from 'd3-zoom';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import { getCombinedGraph, getNote, type GraphSource } from '$lib/api/brain';
	import { getVaultFile } from '$lib/api/vault';

	interface SimNode {
		id: string;
		title: string;
		source: GraphSource;
		kind: string;
		tags: string[];
		backlink_count: number;
		ref: string;
		x?: number;
		y?: number;
		vx?: number;
		vy?: number;
		fx?: number | null;
		fy?: number | null;
	}
	interface SimLink {
		source: string | SimNode;
		target: string | SimNode;
	}

	// ── State ────────────────────────────────────────────────────────────────
	let loading = $state(true);
	let error = $state('');
	let frame = $state(0); // bumped each simulation tick to drive re-render
	let transform = $state({ k: 1, x: 0, y: 0 });
	let width = $state(900);
	let height = $state(620);

	let searchQuery = $state('');
	let sourceEnabled = $state<Record<GraphSource, boolean>>({ vault: true, note: true, action: true });
	let linkByTags = $state(false);
	let hoveredId = $state<string | null>(null);

	let selectedNode = $state<SimNode | null>(null);
	let nodeContent = $state('');
	let contentLoading = $state(false);

	// d3 owns these plain arrays (mutated in place); not reactive on purpose
	let simNodes: SimNode[] = [];
	let simLinks: SimLink[] = [];
	let adjacency = new Map<string, Set<string>>();

	let simulation: Simulation<SimNode, SimLink> | null = null;
	let zoomBehavior: ZoomBehavior<SVGSVGElement, unknown> | null = null;
	let svgEl = $state<SVGSVGElement>();
	let containerEl = $state<HTMLDivElement>();

	const sourceColor: Record<GraphSource, string> = {
		vault: '#00e5ff',
		note: '#39ff14',
		action: '#ffaa00',
	};
	const sourceLabel: Record<GraphSource, string> = {
		vault: 'Vault (~/Memory)',
		note: 'DB Notes',
		action: 'Action Memory',
	};

	function radiusFor(n: { backlink_count: number }): number {
		return 7 + Math.min(16, n.backlink_count * 2);
	}

	// ── Load + simulation ──────────────────────────────────────────────────────
	async function loadGraph() {
		loading = true;
		error = '';
		try {
			const g = await getCombinedGraph(linkByTags);
			startSimulation(g.nodes, g.edges);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load graph';
		} finally {
			loading = false;
		}
	}

	function startSimulation(nodes: SimNode[], edges: { source: string; target: string }[]) {
		simulation?.stop();

		simNodes = nodes.map((n) => ({ ...n }));
		const ids = new Set(simNodes.map((n) => n.id));
		simLinks = edges
			.filter((e) => ids.has(e.source) && ids.has(e.target))
			.map((e) => ({ source: e.source, target: e.target }));

		// adjacency for hover-highlight (uses raw string ids before d3 mutates links)
		adjacency = new Map();
		for (const n of simNodes) adjacency.set(n.id, new Set());
		for (const e of simLinks) {
			adjacency.get(e.source as string)?.add(e.target as string);
			adjacency.get(e.target as string)?.add(e.source as string);
		}

		simulation = forceSimulation<SimNode>(simNodes)
			.force('charge', forceManyBody().strength(-240))
			.force(
				'link',
				forceLink<SimNode, SimLink>(simLinks)
					.id((d) => d.id)
					.distance(75)
					.strength(0.5),
			)
			.force('center', forceCenter(width / 2, height / 2))
			.force('collide', forceCollide<SimNode>().radius((d) => radiusFor(d) + 6))
			.on('tick', () => {
				frame++;
			});
		frame++;
	}

	function neighbors(id: string): Set<string> {
		return adjacency.get(id) ?? new Set();
	}

	function nodeMatches(n: SimNode): boolean {
		const q = searchQuery.trim().toLowerCase();
		if (!q) return true;
		return n.title.toLowerCase().includes(q) || n.tags.some((t) => t.toLowerCase().includes(q));
	}

	// node is rendered at all (source filter)
	function nodeVisible(n: SimNode): boolean {
		return sourceEnabled[n.source];
	}

	// node is emphasized (hover + search), otherwise dimmed
	function nodeActive(n: SimNode): boolean {
		const hoverOk = !hoveredId || hoveredId === n.id || neighbors(hoveredId).has(n.id);
		return hoverOk && nodeMatches(n);
	}

	// ── Derived render snapshots (recompute each tick) ──────────────────────────
	let renderNodes = $derived.by(() => {
		void frame;
		return simNodes.filter(nodeVisible).map((n) => ({
			...n,
			x: n.x ?? width / 2,
			y: n.y ?? height / 2,
			r: radiusFor(n),
			color: sourceColor[n.source],
			active: nodeActive(n),
		}));
	});

	let renderLinks = $derived.by(() => {
		void frame;
		const out: { x1: number; y1: number; x2: number; y2: number; active: boolean }[] = [];
		for (const l of simLinks) {
			const s = l.source as SimNode;
			const t = l.target as SimNode;
			if (typeof s !== 'object' || typeof t !== 'object') continue;
			if (!nodeVisible(s) || !nodeVisible(t)) continue;
			const active =
				(!hoveredId || hoveredId === s.id || hoveredId === t.id) &&
				nodeMatches(s) &&
				nodeMatches(t);
			out.push({ x1: s.x ?? 0, y1: s.y ?? 0, x2: t.x ?? 0, y2: t.y ?? 0, active });
		}
		return out;
	});

	let counts = $derived({
		total: simNodes.length,
		shown: renderNodes.length,
		edges: renderLinks.length,
	});

	// ── Zoom / pan ──────────────────────────────────────────────────────────────
	onMount(() => {
		if (containerEl) {
			width = containerEl.clientWidth || width;
		}
		zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
			.scaleExtent([0.2, 4])
			.on('zoom', (event) => {
				transform = { k: event.transform.k, x: event.transform.x, y: event.transform.y };
			});
		if (svgEl) select(svgEl).call(zoomBehavior);

		const ro = new ResizeObserver(() => {
			if (containerEl) width = containerEl.clientWidth || width;
		});
		if (containerEl) ro.observe(containerEl);

		loadGraph();

		return () => ro.disconnect();
	});

	onDestroy(() => simulation?.stop());

	function zoomToFit() {
		if (!svgEl || !zoomBehavior || renderNodes.length === 0) return;
		let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
		for (const n of renderNodes) {
			minX = Math.min(minX, n.x - n.r);
			minY = Math.min(minY, n.y - n.r);
			maxX = Math.max(maxX, n.x + n.r);
			maxY = Math.max(maxY, n.y + n.r);
		}
		const bw = Math.max(maxX - minX, 1);
		const bh = Math.max(maxY - minY, 1);
		const k = Math.min(4, Math.max(0.2, 0.9 * Math.min(width / bw, height / bh)));
		const tx = width / 2 - k * (minX + bw / 2);
		const ty = height / 2 - k * (minY + bh / 2);
		select(svgEl).call(
			zoomBehavior.transform,
			zoomIdentity.translate(tx, ty).scale(k),
		);
	}

	// ── Node drag (pointer events; d3-drag not installed) ───────────────────────
	let dragId: string | null = null;
	let dragMoved = false;
	let dragStart = { x: 0, y: 0 };

	function toGraphCoords(clientX: number, clientY: number) {
		if (!svgEl) return { x: 0, y: 0 };
		const rect = svgEl.getBoundingClientRect();
		return {
			x: (clientX - rect.left - transform.x) / transform.k,
			y: (clientY - rect.top - transform.y) / transform.k,
		};
	}

	function onNodePointerDown(ev: PointerEvent, id: string) {
		ev.stopPropagation();
		dragId = id;
		dragMoved = false;
		dragStart = { x: ev.clientX, y: ev.clientY };
		const node = simNodes.find((n) => n.id === id);
		if (node) {
			const p = toGraphCoords(ev.clientX, ev.clientY);
			node.fx = p.x;
			node.fy = p.y;
		}
		simulation?.alphaTarget(0.3).restart();
		window.addEventListener('pointermove', onDragMove);
		window.addEventListener('pointerup', onDragEnd);
	}

	function onDragMove(ev: PointerEvent) {
		if (!dragId) return;
		if (Math.abs(ev.clientX - dragStart.x) > 3 || Math.abs(ev.clientY - dragStart.y) > 3) {
			dragMoved = true;
		}
		const node = simNodes.find((n) => n.id === dragId);
		if (node) {
			const p = toGraphCoords(ev.clientX, ev.clientY);
			node.fx = p.x;
			node.fy = p.y;
		}
	}

	function onDragEnd() {
		const id = dragId;
		const moved = dragMoved;
		window.removeEventListener('pointermove', onDragMove);
		window.removeEventListener('pointerup', onDragEnd);
		simulation?.alphaTarget(0);
		const node = simNodes.find((n) => n.id === id);
		if (node) {
			node.fx = null;
			node.fy = null;
		}
		dragId = null;
		if (!moved && id) {
			const n = simNodes.find((s) => s.id === id);
			if (n) openNode(n);
		}
	}

	// ── Open node content ───────────────────────────────────────────────────────
	async function openNode(n: SimNode) {
		selectedNode = n;
		nodeContent = '';
		if (n.source === 'action') return; // show fields directly, no fetch
		contentLoading = true;
		try {
			if (n.source === 'vault') {
				const r = await getVaultFile(n.ref);
				nodeContent = r.content;
			} else if (n.source === 'note') {
				const note = await getNote(Number(n.ref));
				nodeContent = note.content;
			}
		} catch (e) {
			nodeContent = `Failed to load: ${e instanceof Error ? e.message : 'unknown error'}`;
		} finally {
			contentLoading = false;
		}
	}

	function closePanel() {
		selectedNode = null;
		nodeContent = '';
	}

	function toggleSource(s: GraphSource) {
		sourceEnabled = { ...sourceEnabled, [s]: !sourceEnabled[s] };
	}

	function toggleLinkTags() {
		linkByTags = !linkByTags;
		loadGraph();
	}
</script>

<svelte:head>
	<title>BorgOS — Obsidian Graph</title>
</svelte:head>

<div class="graph-page">
	<header class="module-header">
		<h1>OBSIDIAN GRAPH</h1>
		<p class="subtitle">
			{counts.shown}/{counts.total} nodes · {counts.edges} connections — vault, notes &amp; actions
		</p>
	</header>

	{#if error}
		<div class="error-banner" role="alert">{error}</div>
	{:else if loading}
		<div class="loading-text">LOADING GRAPH...</div>
	{:else}
		<div class="toolbar">
			<div class="search-box">
				<BorgInput bind:value={searchQuery} placeholder="Search title or #tag…" />
			</div>
			<div class="filters">
				{#each ['vault', 'note', 'action'] as const as s}
					<button
						class="filter-chip"
						class:filter-chip--off={!sourceEnabled[s]}
						style:--chip={sourceColor[s]}
						onclick={() => toggleSource(s)}
						type="button"
					>
						<span class="chip-dot"></span>{sourceLabel[s]}
					</button>
				{/each}
			</div>
			<div class="actions">
				<BorgButton variant={linkByTags ? 'primary' : 'secondary'} onclick={toggleLinkTags}>
					LINK BY TAGS
				</BorgButton>
				<BorgButton variant="secondary" onclick={zoomToFit}>ZOOM TO FIT</BorgButton>
				<BorgButton variant="secondary" onclick={loadGraph}>REFRESH</BorgButton>
			</div>
		</div>

		<div class="graph-layout">
			<BorgPanel class="graph-panel">
				<div class="canvas-wrap" bind:this={containerEl}>
					{#if counts.total === 0}
						<div class="empty-state">
							<p>No memory yet. Create notes with [[wiki-links]] in ~/Memory/ or the Second Brain to build your graph.</p>
						</div>
					{:else}
						<svg
							bind:this={svgEl}
							class="graph-svg"
							{width}
							{height}
							viewBox={`0 0 ${width} ${height}`}
							role="application"
							aria-label="Knowledge graph"
						>
							<g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.k})`}>
								{#each renderLinks as link}
									<line
										x1={link.x1}
										y1={link.y1}
										x2={link.x2}
										y2={link.y2}
										class="edge"
										stroke-opacity={link.active ? 0.45 : 0.08}
									/>
								{/each}

								{#each renderNodes as node (node.id)}
									<g
										class="node"
										class:selected={selectedNode?.id === node.id}
										transform={`translate(${node.x}, ${node.y})`}
										opacity={node.active ? 1 : 0.25}
										onpointerdown={(e) => onNodePointerDown(e, node.id)}
										onmouseenter={() => (hoveredId = node.id)}
										onmouseleave={() => (hoveredId = null)}
										role="button"
										tabindex="-1"
									>
										<circle r={node.r} fill="var(--borg-void)" stroke={node.color} stroke-width="2" />
										<text
											class="node-label"
											text-anchor="middle"
											dy={node.r + 12}
											fill="var(--borg-text-secondary)"
										>
											{node.title.length > 18 ? node.title.slice(0, 18) + '…' : node.title}
										</text>
									</g>
								{/each}
							</g>
						</svg>

						<div class="legend">
							{#each ['vault', 'note', 'action'] as const as s}
								<span class="legend-item">
									<span class="legend-dot" style:background={sourceColor[s]}></span>{sourceLabel[s]}
								</span>
							{/each}
						</div>
					{/if}
				</div>
			</BorgPanel>

			{#if selectedNode}
				<BorgPanel class="detail-panel">
					<div class="panel-head">
						<span class="detail-title">{selectedNode.title}</span>
						<button class="close-btn" onclick={closePanel} aria-label="Close">×</button>
					</div>

					<div class="detail-meta">
						<span class="detail-badge" style:--chip={sourceColor[selectedNode.source]}>
							{sourceLabel[selectedNode.source]}
						</span>
						<span class="detail-kind">{selectedNode.kind}</span>
					</div>
					{#if selectedNode.tags.length > 0}
						<div class="detail-tags">
							{#each selectedNode.tags as tag}<span class="tag">#{tag}</span>{/each}
						</div>
					{/if}

					{#if selectedNode.source === 'action'}
						<p class="detail-note">Action memory — open Action Memory page for full details.</p>
					{:else if contentLoading}
						<p class="detail-note">Loading content…</p>
					{:else}
						<pre class="detail-content">{nodeContent}</pre>
					{/if}
				</BorgPanel>
			{/if}
		</div>
	{/if}
</div>

<style>
	.graph-page {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.module-header h1 {
		font-size: 24px;
		color: var(--borg-cyan);
		letter-spacing: 0.15em;
		margin: 0 0 8px;
		font-family: 'Share Tech Mono', monospace;
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

	.loading-text {
		padding: 48px;
		text-align: center;
		color: var(--borg-cyan);
		font-size: 12px;
		letter-spacing: 0.1em;
	}

	.toolbar {
		display: flex;
		gap: 12px;
		align-items: center;
		flex-wrap: wrap;
	}

	.search-box {
		flex: 1;
		min-width: 200px;
		max-width: 360px;
	}

	.filters {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	.filter-chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		background: var(--borg-void);
		border: 1px solid var(--borg-border);
		color: var(--borg-text-primary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		padding: 5px 10px;
		cursor: pointer;
		transition: all 120ms ease-out;
	}

	.filter-chip:hover {
		border-color: var(--chip);
	}

	.filter-chip--off {
		opacity: 0.4;
	}

	.chip-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--chip);
	}

	.actions {
		display: flex;
		gap: 8px;
		margin-left: auto;
	}

	.graph-layout {
		display: flex;
		gap: 16px;
		align-items: stretch;
	}

	:global(.graph-panel) {
		flex: 1;
		overflow: hidden;
	}

	.canvas-wrap {
		position: relative;
		width: 100%;
	}

	.graph-svg {
		width: 100%;
		height: 620px;
		display: block;
		cursor: grab;
		background:
			radial-gradient(circle at 20% 20%, rgba(0, 229, 255, 0.04), transparent 60%),
			radial-gradient(circle at 80% 70%, rgba(57, 255, 20, 0.03), transparent 60%);
	}

	.graph-svg:active {
		cursor: grabbing;
	}

	.edge {
		stroke: var(--borg-cyan);
		stroke-width: 1;
		transition: stroke-opacity 120ms ease-out;
	}

	.node {
		cursor: pointer;
		transition: opacity 120ms ease-out;
	}

	.node:hover circle {
		stroke-width: 3;
		filter: drop-shadow(0 0 6px currentColor);
	}

	.node.selected circle {
		stroke-width: 3;
		filter: drop-shadow(0 0 10px var(--borg-green));
	}

	.node-label {
		font-size: 9px;
		font-family: 'JetBrains Mono', monospace;
		pointer-events: none;
		user-select: none;
	}

	.legend {
		position: absolute;
		bottom: 10px;
		left: 10px;
		display: flex;
		gap: 14px;
		background: rgba(8, 11, 13, 0.7);
		border: 1px solid var(--borg-border);
		padding: 6px 10px;
		font-size: 10px;
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-text-secondary);
	}

	.legend-item {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}

	.legend-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}

	.empty-state {
		padding: 80px 48px;
		text-align: center;
		color: var(--borg-text-secondary);
		font-size: 13px;
	}

	/* Detail panel */
	:global(.detail-panel) {
		width: 380px;
		min-width: 380px;
		max-height: 700px;
		overflow-y: auto;
	}

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
</style>
