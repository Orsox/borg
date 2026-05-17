<script lang="ts">
	import { onMount } from 'svelte';
	import {
		scanAssets,
		listAssets,
		copyAsset,
		toggleFavorite,
		getCopyHistory,
		type Asset,
		type CopyHistoryItem
	} from '$lib/api/archon';
	import { toastStore } from '$lib/stores/toast';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import HexLoader from '$lib/components/HexLoader.svelte';

	let assets = $state<Asset[]>([]);
	let total = $state(0);
	let currentPage = $state(1);
	let totalPages = $state(0);
	let loading = $state(false);
	let scanning = $state(false);
	let lastScanned = $state<string | null>(null);
	let searchTerm = $state('');
	let activeFilter = $state('all');
	let selectedAsset = $state<Asset | null>(null);
	let showHistory = $state(false);
	let copyHistory = $state<CopyHistoryItem[]>([]);
	let searchTimeout: ReturnType<typeof setTimeout>;

	const filterTypes = ['all', 'workflow', 'skill', 'agent'];

	async function loadAssets(page = 1) {
		loading = true;
		try {
			const result = await listAssets({
				page,
				size: 12,
				type: activeFilter === 'all' ? undefined : activeFilter,
				search: searchTerm || undefined
			});
			assets = result.items;
			total = result.total;
			currentPage = result.page;
			totalPages = result.pages;
		} catch (e) {
			toastStore.error('Failed to load assets');
		} finally {
			loading = false;
		}
	}

	async function handleScan() {
		scanning = true;
		try {
			const result = await scanAssets();
			lastScanned = result.scanned_at;
			toastStore.success(`Scan complete — ${result.count} assets indexed`);
			await loadAssets(1);
		} catch (e: any) {
			toastStore.error(e.message ?? 'Scan failed');
		} finally {
			scanning = false;
		}
	}

	async function handleCopy(asset: Asset, e?: MouseEvent) {
		e?.stopPropagation();
		try {
			const result = await copyAsset(asset.id);
			toastStore.success(`Copied to ${result.destination_path}`);
		} catch (err: any) {
			toastStore.error(err.message ?? 'Copy failed');
		}
	}

	async function handleToggleFavorite(asset: Asset, e?: MouseEvent) {
		e?.stopPropagation();
		try {
			const result = await toggleFavorite(asset.id);
			asset.is_favorite = result.is_favorite;
			assets = assets.map(a => a.id === asset.id ? { ...a, is_favorite: result.is_favorite } : a);
			if (selectedAsset?.id === asset.id) {
				selectedAsset = { ...selectedAsset, is_favorite: result.is_favorite };
			}
		} catch (err: any) {
			toastStore.error(err.message ?? 'Failed to update favorite');
		}
	}

	function handleSearch() {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => loadAssets(1), 300);
	}

	async function openHistory() {
		showHistory = true;
		try {
			copyHistory = await getCopyHistory();
		} catch {
			toastStore.error('Failed to load copy history');
		}
	}

	function formatDate(iso: string) {
		return new Date(iso).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	const typeColor: Record<string, string> = {
		workflow: 'var(--borg-cyan)',
		skill: 'var(--borg-green)',
		agent: 'var(--borg-amber)',
		unknown: 'var(--borg-text-secondary)'
	};

	onMount(() => loadAssets());
</script>

<svelte:head>
	<title>BorgOS — Archon Hub</title>
</svelte:head>

<div class="archon-hub">
	<!-- Header -->
	<header class="module-header">
		<div class="header-left">
			<h1>ARCHON HUB</h1>
			{#if lastScanned}
				<span class="scan-time">Last scan: {formatDate(lastScanned)}</span>
			{/if}
		</div>
		<div class="header-actions">
			<BorgButton variant="ghost" onclick={openHistory}>
				Copy History
			</BorgButton>
			<BorgButton variant="secondary" onclick={handleScan} disabled={scanning}>
				{#if scanning}
					<HexLoader size={16} />
					SCANNING...
				{:else}
					↺ RE-SCAN
				{/if}
			</BorgButton>
		</div>
	</header>

	<!-- Filters and Search -->
	<div class="toolbar">
		<div class="filter-tabs" role="tablist" aria-label="Asset type filter">
			{#each filterTypes as filter}
				<button
					class="filter-tab"
					class:filter-tab--active={activeFilter === filter}
					role="tab"
					aria-selected={activeFilter === filter}
					onclick={() => { activeFilter = filter; loadAssets(1); }}
				>
					{filter.toUpperCase()}
				</button>
			{/each}
		</div>
		<BorgInput
			type="text"
			bind:value={searchTerm}
			placeholder="Search assets..."
			oninput={handleSearch}
			class="search-input"
		/>
	</div>

	<!-- Asset count -->
	<div class="asset-count">
		{#if loading}
			<span>Loading...</span>
		{:else}
			<span>{total} asset{total !== 1 ? 's' : ''} found</span>
		{/if}
	</div>

	<!-- Asset Grid -->
	{#if loading}
		<div class="loading-state">
			<HexLoader size={48} />
		</div>
	{:else if assets.length === 0}
		<div class="empty-state">
			<p>No assets found.</p>
			<p>Click RE-SCAN to index assets from ARCHON_PATH.</p>
		</div>
	{:else}
		<div class="asset-grid">
			{#each assets as asset (asset.id)}
				<BorgPanel class="asset-card">
					<div class="asset-card-inner" onclick={() => selectedAsset = asset} role="button" tabindex="0" onkeydown={(e) => e.key === 'Enter' && (selectedAsset = asset)} aria-label="View {asset.name} details">
						<div class="asset-card-header">
							<span class="asset-type-badge" style="color: {typeColor[asset.type] ?? typeColor.unknown}; border-color: {typeColor[asset.type] ?? typeColor.unknown}">
								{asset.type}
							</span>
							<button
								class="favorite-btn"
								class:favorite-btn--active={asset.is_favorite}
								onclick={(e) => { e.stopPropagation(); handleToggleFavorite(asset); }}
								aria-label="{asset.is_favorite ? 'Remove from' : 'Add to'} favorites"
							>★</button>
						</div>

						<h3 class="asset-name">{asset.name}</h3>

						{#if asset.description}
							<p class="asset-desc">{asset.description}</p>
						{/if}

						{#if asset.tags.length > 0}
							<div class="asset-tags">
								{#each asset.tags.slice(0, 3) as tag}
									<span class="tag">{tag}</span>
								{/each}
							</div>
						{/if}

						<div class="asset-footer">
							<BorgButton
								variant="primary"
								onclick={(e) => { e?.stopPropagation(); handleCopy(asset); }}
								class="copy-btn"
							>
								COPY
							</BorgButton>
						</div>
					</div>
				</BorgPanel>
			{/each}
		</div>

		<!-- Pagination -->
		{#if totalPages > 1}
			<div class="pagination">
				<BorgButton variant="ghost" disabled={currentPage <= 1} onclick={() => loadAssets(currentPage - 1)}>
					← PREV
				</BorgButton>
				<span class="page-info">Page {currentPage} of {totalPages}</span>
				<BorgButton variant="ghost" disabled={currentPage >= totalPages} onclick={() => loadAssets(currentPage + 1)}>
					NEXT →
				</BorgButton>
			</div>
		{/if}
	{/if}
</div>

<!-- Asset Detail Panel -->
{#if selectedAsset}
	<div class="overlay" onclick={() => selectedAsset = null} role="dialog" aria-modal="true" aria-label="Asset detail">
		<div class="detail-panel" onclick={(e) => e.stopPropagation()}>
			<div class="detail-header">
				<div>
					<span class="asset-type-badge" style="color: {typeColor[selectedAsset.type] ?? typeColor.unknown}; border-color: {typeColor[selectedAsset.type] ?? typeColor.unknown}">
						{selectedAsset.type}
					</span>
					<h2 class="detail-title">{selectedAsset.name}</h2>
				</div>
				<div class="detail-actions">
					<button
						class="favorite-btn"
						class:favorite-btn--active={selectedAsset.is_favorite}
						onclick={() => selectedAsset && handleToggleFavorite(selectedAsset)}
						aria-label="{selectedAsset.is_favorite ? 'Remove from' : 'Add to'} favorites"
					>★</button>
					<BorgButton variant="secondary" onclick={() => selectedAsset && handleCopy(selectedAsset)}>
						COPY TO SYSTEM
					</BorgButton>
					<BorgButton variant="ghost" onclick={() => selectedAsset = null} aria-label="Close panel">
						✕ CLOSE
					</BorgButton>
				</div>
			</div>

			{#if selectedAsset.description}
				<p class="detail-desc">{selectedAsset.description}</p>
			{/if}

			{#if selectedAsset.tags.length > 0}
				<div class="asset-tags" style="margin-bottom: 16px;">
					{#each selectedAsset.tags as tag}
						<span class="tag">{tag}</span>
					{/each}
				</div>
			{/if}

			<div class="detail-meta">
				<span>Path: <code>{selectedAsset.file_path}</code></span>
				<span>Scanned: {formatDate(selectedAsset.last_scanned)}</span>
			</div>

			<div class="raw-content-header">RAW CONTENT</div>
			<pre class="raw-content"><code>{selectedAsset.raw_content}</code></pre>
		</div>
	</div>
{/if}

<!-- Copy History Drawer -->
{#if showHistory}
	<div class="overlay" onclick={() => showHistory = false} role="dialog" aria-modal="true" aria-label="Copy history">
		<div class="history-panel" onclick={(e) => e.stopPropagation()}>
			<div class="detail-header">
				<h2 class="detail-title">COPY HISTORY</h2>
				<BorgButton variant="ghost" onclick={() => showHistory = false} aria-label="Close history">
					✕ CLOSE
				</BorgButton>
			</div>

			{#if copyHistory.length === 0}
				<p class="empty-state">No copy operations yet.</p>
			{:else}
				<div class="history-list">
					{#each copyHistory as item}
						<div class="history-item">
							<div class="history-name">{item.asset_name}</div>
							<div class="history-path">→ {item.destination_path}</div>
							<div class="history-time">{formatDate(item.copied_at)}</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.archon-hub {
		max-width: 1400px;
	}

	.module-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 24px;
		padding-bottom: 16px;
		border-bottom: 1px solid var(--borg-border);
	}

	.module-header h1 {
		font-size: 24px;
		color: var(--borg-cyan);
		letter-spacing: 0.15em;
		margin: 0 0 4px;
	}

	.scan-time {
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	.header-actions {
		display: flex;
		gap: 8px;
		align-items: center;
	}

	.toolbar {
		display: flex;
		gap: 16px;
		margin-bottom: 16px;
		align-items: center;
		flex-wrap: wrap;
	}

	.filter-tabs {
		display: flex;
		gap: 0;
		border: 1px solid var(--borg-border);
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

	:global(.search-input) {
		max-width: 300px;
		flex: 1;
	}

	.asset-count {
		font-size: 12px;
		color: var(--borg-text-secondary);
		margin-bottom: 16px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.loading-state, .empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 64px;
		color: var(--borg-text-secondary);
		gap: 16px;
	}

	.asset-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 12px;
	}

	:global(.asset-card) {
		transition: border-color 150ms ease-out;
		cursor: pointer;
	}

	:global(.asset-card:hover) {
		border-color: var(--borg-border-active);
	}

	.asset-card-inner {
		background: none;
		border: none;
		padding: 16px;
		text-align: left;
		cursor: pointer;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.asset-card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.asset-type-badge {
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		font-weight: 600;
		padding: 2px 8px;
		border: 1px solid;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		clip-path: polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%);
	}

	.favorite-btn {
		background: none;
		border: none;
		font-size: 16px;
		cursor: pointer;
		color: var(--borg-text-disabled);
		transition: color 150ms ease-out;
		padding: 0;
		line-height: 1;
	}

	.favorite-btn--active {
		color: var(--borg-amber);
	}

	.favorite-btn:hover {
		color: var(--borg-amber);
	}

	.asset-name {
		font-family: 'Share Tech Mono', monospace;
		font-size: 14px;
		color: var(--borg-text-primary);
		margin: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.asset-desc {
		font-size: 12px;
		color: var(--borg-text-secondary);
		margin: 0;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.asset-tags {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
	}

	.tag {
		font-size: 10px;
		padding: 2px 6px;
		background-color: rgba(0, 229, 255, 0.08);
		border: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		letter-spacing: 0.05em;
	}

	.asset-footer {
		margin-top: 4px;
	}

	:global(.copy-btn) {
		font-size: 11px !important;
		padding: 4px 12px !important;
	}

	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 16px;
		margin-top: 24px;
	}

	.page-info {
		font-size: 12px;
		color: var(--borg-text-secondary);
	}

	/* Overlay and panels */
	.overlay {
		position: fixed;
		inset: 0;
		background-color: rgba(8, 11, 13, 0.8);
		z-index: 200;
		display: flex;
		justify-content: flex-end;
	}

	.detail-panel, .history-panel {
		background-color: var(--borg-panel);
		border-left: 1px solid var(--borg-border);
		width: 600px;
		max-width: 90vw;
		height: 100vh;
		overflow-y: auto;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.detail-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 16px;
	}

	.detail-title {
		font-family: 'Share Tech Mono', monospace;
		font-size: 20px;
		color: var(--borg-text-primary);
		margin: 8px 0 0;
		letter-spacing: 0.05em;
	}

	.detail-actions {
		display: flex;
		gap: 8px;
		align-items: center;
		flex-shrink: 0;
	}

	.detail-desc {
		color: var(--borg-text-secondary);
		font-size: 13px;
		margin: 0;
		line-height: 1.6;
	}

	.detail-meta {
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	.detail-meta code {
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-text-primary);
	}

	.raw-content-header {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--borg-cyan);
		padding-bottom: 8px;
		border-bottom: 1px solid var(--borg-border);
	}

	.raw-content {
		background-color: var(--borg-black);
		border: 1px solid var(--borg-border);
		padding: 16px;
		overflow-x: auto;
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		color: var(--borg-text-primary);
		margin: 0;
		flex: 1;
		white-space: pre-wrap;
		word-break: break-all;
	}

	.history-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.history-item {
		background-color: var(--borg-void);
		border: 1px solid var(--borg-border);
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.history-name {
		font-size: 13px;
		color: var(--borg-text-primary);
		font-weight: 600;
	}

	.history-path {
		font-size: 11px;
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		word-break: break-all;
	}

	.history-time {
		font-size: 11px;
		color: var(--borg-text-disabled);
	}
</style>
