<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import { getKnowledgeGraph } from '$lib/api/brain';
	import type { GraphNode, GraphEdge } from '$lib/api/brain';

	let nodes = $state<GraphNode[]>([]);
	let edges = $state<GraphEdge[]>([]);
	let loading = $state(true);
	let error = $state('');
	let selectedNodeId = $state<number | null>(null);

	// Simple force-directed layout
	let nodePositions = $state<Map<number, { x: number; y: number }>>(new Map());
	let canvasWidth = $state(800);
	let canvasHeight = $state(500);

	async function loadGraph() {
		try {
			const graph = await getKnowledgeGraph();
			nodes = graph.nodes;
			edges = graph.edges;
			initializePositions();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load graph';
		} finally {
			loading = false;
		}
	}

	function initializePositions() {
		const positions = new Map<number, { x: number; y: number }>();
		const centerX = canvasWidth / 2;
		const centerY = canvasHeight / 2;
		const radius = Math.min(canvasWidth, canvasHeight) * 0.35;

		nodes.forEach((node, i) => {
			const angle = (2 * Math.PI * i) / Math.max(nodes.length, 1);
			positions.set(node.id, {
				x: centerX + radius * Math.cos(angle),
				y: centerY + radius * Math.sin(angle),
			});
		});

		nodePositions = positions;
	}

	function zoomToFit() {
		initializePositions();
	}

	function handleNodeClick(nodeId: number) {
		if (selectedNodeId === nodeId) {
			window.location.href = `/brain?id=${nodeId}`;
		} else {
			selectedNodeId = nodeId;
		}
	}

	const tagColors = [
		'#00e5ff', '#39ff14', '#ffaa00', '#ff2244',
		'#aa88ff', '#ff88aa', '#88ffaa', '#88aaff',
	];

	function getTagColor(tag: string): string {
		let hash = 0;
		for (let i = 0; i < tag.length; i++) {
			hash = tag.charCodeAt(i) + ((hash << 5) - hash);
		}
		return tagColors[Math.abs(hash) % tagColors.length];
	}

	onMount(loadGraph);
</script>

<svelte:head>
	<title>BorgOS — Knowledge Graph</title>
</svelte:head>

<div class="graph-container">
	<header class="module-header">
		<h1>KNOWLEDGE GRAPH</h1>
		<p class="subtitle">{nodes.length} nodes · {edges.length} connections</p>
	</header>

	{#if error}
		<div class="error-banner" role="alert">{error}</div>
	{:else if loading}
		<div class="loading-text">LOADING GRAPH...</div>
	{:else}
		<div class="graph-controls">
			<BorgButton variant="secondary" onclick={zoomToFit}>ZOOM TO FIT</BorgButton>
			<BorgButton variant="secondary" onclick={loadGraph}>REFRESH</BorgButton>
			<a href="/brain" class="graph-link">← BACK TO NOTES</a>
		</div>

		{#if nodes.length === 0}
			<BorgPanel class="empty-graph">
				<div class="empty-state">
					<p>No notes yet. Create notes with [[wiki-links]] to build your knowledge graph.</p>
				</div>
			</BorgPanel>
		{:else}
			<BorgPanel class="graph-panel">
				<svg
					class="graph-svg"
					width={canvasWidth}
					height={canvasHeight}
					viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
				>
					<!-- Edges -->
					{#each edges as edge (edge.source + '-' + edge.target)}
						{@const sourcePos = nodePositions.get(edge.source)}
						{@const targetPos = nodePositions.get(edge.target)}
						{#if sourcePos && targetPos}
							<line
								x1={sourcePos.x}
								y1={sourcePos.y}
								x2={targetPos.x}
								y2={targetPos.y}
								class="graph-edge"
								stroke="var(--borg-cyan)"
								stroke-width="1"
								stroke-opacity="0.3"
							/>
						{/if}
					{/each}

					<!-- Nodes -->
					{#each nodes as node (node.id)}
						{@const pos = nodePositions.get(node.id)}
						{#if pos}
							<g
								class="graph-node {selectedNodeId === node.id ? 'selected' : ''}"
								onclick={() => handleNodeClick(node.id)}
								transform={`translate(${pos.x}, ${pos.y})`}
							>
								<circle
									r="20"
									fill="var(--borg-void)"
									stroke={node.tags.length > 0 ? getTagColor(node.tags[0]) : 'var(--borg-cyan)'}
									stroke-width="2"
								/>
								<text
									text-anchor="middle"
									dy="0.35em"
									fill="var(--borg-text-primary)"
									font-size="10"
									font-family="'JetBrains Mono', monospace"
								>
									{node.title.length > 8 ? node.title.slice(0, 8) + '…' : node.title}
								</text>
							</g>
						{/if}
					{/each}
				</svg>
			</BorgPanel>
		{/if}
	{/if}
</div>

<style>
	.graph-container {
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

	.graph-controls {
		display: flex;
		gap: 8px;
		align-items: center;
	}

	.graph-link {
		color: var(--borg-cyan);
		font-size: 12px;
		text-decoration: none;
		margin-left: auto;
	}

	.graph-link:hover {
		text-decoration: underline;
	}

	.graph-panel {
		overflow: hidden;
	}

	.graph-svg {
		width: 100%;
		height: auto;
	}

	.graph-node {
		cursor: pointer;
		transition: all 150ms ease-out;
	}

	.graph-node:hover circle {
		stroke-width: 3;
		filter: drop-shadow(0 0 6px var(--borg-cyan));
	}

	.graph-node.selected circle {
		stroke-width: 3;
		filter: drop-shadow(0 0 10px var(--borg-green));
	}

	.empty-graph {
		padding: 48px;
		text-align: center;
	}

	.empty-state {
		color: var(--borg-text-secondary);
		font-size: 13px;
	}

	.loading-text {
		padding: 48px;
		text-align: center;
		color: var(--borg-cyan);
		font-size: 12px;
		letter-spacing: 0.1em;
	}
</style>
