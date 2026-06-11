<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BrainItemPanel, {
		sourceColor,
		sourceLabel,
		type BrainItemRef,
	} from '$lib/components/BrainItemPanel.svelte';
	import NoteEditor from '$lib/components/NoteEditor.svelte';
	import BrainGraphView from '$lib/components/BrainGraphView.svelte';
	import InsightsPanel from '$lib/components/InsightsPanel.svelte';
	import { searchBrain, createNote, type BrainSearchResult, type GraphSource } from '$lib/api/brain';
	import { listDrafts, getHabits, getHeartbeatStatus } from '$lib/api/vault';

	const ALL_SOURCES: GraphSource[] = ['note', 'vault', 'action'];

	// ── Workspace state (seeded from URL) ───────────────────────────────────────
	const initParams = $page.url.searchParams;

	let query = $state(initParams.get('q') ?? '');
	let view = $state<'list' | 'graph'>(initParams.get('view') === 'graph' ? 'graph' : 'list');
	let insightsOpen = $state(initParams.get('insights') === '1');
	let sourceEnabled = $state<Record<GraphSource, boolean>>(parseSources(initParams.get('sources')));
	let selectedItem = $state<BrainItemRef | null>(parseInitialItem(initParams));

	let items = $state<BrainSearchResult[]>([]);
	let loading = $state(true);
	let error = $state('');

	// Vault status strip
	let draftCount = $state<number | null>(null);
	let habitsDone = $state<[number, number] | null>(null);
	let heartbeatAge = $state<string | null>(null);

	function parseSources(raw: string | null): Record<GraphSource, boolean> {
		const enabled: Record<GraphSource, boolean> = { note: true, vault: true, action: true };
		if (!raw) return enabled;
		const wanted = new Set(raw.split(',').map((s) => s.trim()));
		let any = false;
		for (const s of ALL_SOURCES) {
			enabled[s] = wanted.has(s);
			any = any || enabled[s];
		}
		return any ? enabled : { note: true, vault: true, action: true };
	}

	function parseInitialItem(params: URLSearchParams): BrainItemRef | null {
		const noteParam = params.get('note'); // legacy deep link
		const itemParam = noteParam ? `note:${noteParam}` : params.get('item');
		return itemParam ? itemFromId(itemParam) : null;
	}

	function itemFromId(id: string): BrainItemRef | null {
		const sep = id.indexOf(':');
		if (sep === -1) return null;
		const source = id.slice(0, sep) as GraphSource;
		if (!ALL_SOURCES.includes(source)) return null;
		const ref = id.slice(sep + 1);
		// Placeholder until the list loads and fills in real metadata.
		return { id, title: ref, source, kind: '', tags: [], ref };
	}

	let enabledSources = $derived(ALL_SOURCES.filter((s) => sourceEnabled[s]));

	// ── Data loading ─────────────────────────────────────────────────────────────
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;
	let loadSeq = 0;

	async function loadItems() {
		const seq = ++loadSeq;
		loading = true;
		try {
			const r = await searchBrain(query.trim(), enabledSources, 100);
			if (seq !== loadSeq) return; // stale response
			items = r.results;
			error = '';
			// Upgrade a URL-seeded placeholder with real metadata once known.
			if (selectedItem && !selectedItem.kind) {
				const match = items.find((i) => i.id === selectedItem!.id);
				if (match) selectedItem = match;
			}
		} catch (e) {
			if (seq !== loadSeq) return;
			error = e instanceof Error ? e.message : 'Failed to load items';
		} finally {
			if (seq === loadSeq) loading = false;
		}
	}

	$effect(() => {
		void query;
		void enabledSources;
		clearTimeout(debounceTimer);
		debounceTimer = setTimeout(loadItems, 250);
		return () => clearTimeout(debounceTimer);
	});

	async function loadVaultStrip() {
		try {
			draftCount = (await listDrafts()).length;
		} catch {
			draftCount = null;
		}
		try {
			const habits = await getHabits();
			habitsDone = habits.length > 0 ? [habits.filter((h) => h.checked).length, habits.length] : null;
		} catch {
			habitsDone = null;
		}
		const hb = await getHeartbeatStatus();
		if (hb?.timestamp) {
			const mins = Math.round((Date.now() - new Date(hb.timestamp).getTime()) / 60000);
			heartbeatAge = mins < 60 ? `${mins}m` : `${Math.round(mins / 60)}h`;
		}
	}

	onMount(loadVaultStrip);

	// ── URL sync (state → URL) ───────────────────────────────────────────────────
	function syncUrl() {
		const params = new URLSearchParams();
		if (query.trim()) params.set('q', query.trim());
		if (enabledSources.length < ALL_SOURCES.length) params.set('sources', enabledSources.join(','));
		if (view === 'graph') params.set('view', 'graph');
		if (insightsOpen) params.set('insights', '1');
		if (selectedItem) params.set('item', selectedItem.id);
		const qs = params.toString();
		goto(qs ? `/brain?${qs}` : '/brain', { replaceState: true, keepFocus: true, noScroll: true });
	}

	// URL → state, for in-app links like the panel's OPEN IN EDITOR (?note=N).
	$effect(() => {
		const noteParam = $page.url.searchParams.get('note');
		if (noteParam && selectedItem?.id !== `note:${noteParam}`) {
			selectedItem = itemFromId(`note:${noteParam}`);
			view = 'list';
			syncUrl();
		}
	});

	// ── Interactions ─────────────────────────────────────────────────────────────
	function toggleSource(s: GraphSource) {
		const next = { ...sourceEnabled, [s]: !sourceEnabled[s] };
		if (!next.note && !next.vault && !next.action) return; // keep at least one
		sourceEnabled = next;
		if (selectedItem && !next[selectedItem.source]) selectedItem = null;
		syncUrl();
	}

	function setView(v: 'list' | 'graph') {
		view = v;
		syncUrl();
	}

	function toggleInsights() {
		insightsOpen = !insightsOpen;
		syncUrl();
	}

	function selectItem(item: BrainItemRef | null) {
		selectedItem = item;
		syncUrl();
	}

	async function newNote() {
		try {
			const note = await createNote('Untitled Note', '', []);
			await loadItems();
			selectItem({
				id: `note:${note.id}`,
				title: note.title,
				source: 'note',
				kind: 'db-note',
				tags: [],
				ref: String(note.id),
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create note';
		}
	}

	function onNoteSaved() {
		loadItems();
	}

	function onNoteArchived() {
		selectItem(null);
		loadItems();
	}

	function onBacklinkNavigate(id: number) {
		selectItem(itemFromId(`note:${id}`));
	}

	function formatTime(dateStr: string | null): string {
		if (!dateStr) return '';
		return new Date(dateStr).toLocaleDateString('en-GB', {
			day: '2-digit',
			month: 'short',
		});
	}
</script>

<svelte:head>
	<title>BorgOS — Second Brain</title>
</svelte:head>

<div class="workspace">
	<header class="module-header">
		<h1>SECOND BRAIN</h1>
		<p class="subtitle">One memory — notes, vault &amp; actions</p>
	</header>

	<!-- Toolbar: search · source filters · view toggle · insights · vault strip -->
	<div class="toolbar">
		<div class="search-box">
			<BorgInput bind:value={query} placeholder="Search everything…" />
		</div>

		<div class="filters">
			{#each ALL_SOURCES as s}
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

		<div class="view-toggle" role="tablist" aria-label="View">
			<button
				class="view-tab"
				class:view-tab--active={view === 'list'}
				role="tab"
				aria-selected={view === 'list'}
				onclick={() => setView('list')}
			>
				◉ LIST
			</button>
			<button
				class="view-tab"
				class:view-tab--active={view === 'graph'}
				role="tab"
				aria-selected={view === 'graph'}
				onclick={() => setView('graph')}
			>
				⊛ GRAPH
			</button>
		</div>

		<button
			class="insights-toggle"
			class:insights-toggle--active={insightsOpen}
			onclick={toggleInsights}
			type="button"
		>
			◎ INSIGHTS
		</button>

		<div class="vault-strip">
			{#if draftCount !== null}<span>drafts {draftCount}</span>{/if}
			{#if habitsDone}<span>habits {habitsDone[0]}/{habitsDone[1]}</span>{/if}
			{#if heartbeatAge}<span>♥ {heartbeatAge} ago</span>{/if}
			<a href="/brain/vault">VAULT OPS →</a>
		</div>
	</div>

	{#if insightsOpen}
		<InsightsPanel />
	{/if}

	{#if error}
		<div class="error-banner" role="alert">{error}</div>
	{/if}

	{#if view === 'list'}
		<div class="list-layout">
			<BorgPanel class="item-list-panel">
				<div class="item-list-header">
					<BorgButton variant="primary" onclick={newNote}>+ NEW NOTE</BorgButton>
					<span class="item-count">{items.length} items</span>
				</div>
				{#if loading && items.length === 0}
					<div class="loading-text">LOADING...</div>
				{:else if items.length === 0}
					<div class="empty-state">Nothing here — adjust filters or create a note.</div>
				{:else}
					<ul class="item-list">
						{#each items as item (item.id)}
							<li>
								<button
									type="button"
									class="item-row"
									class:item-row--selected={selectedItem?.id === item.id}
									style:--chip={sourceColor[item.source]}
									onclick={() => selectItem(item)}
								>
									<span class="item-row-head">
										<span class="chip-dot"></span>
										<span class="item-title">{item.title}</span>
										<span class="item-date">{formatTime(item.updated_at)}</span>
									</span>
									<span class="item-row-meta">
										<span class="item-kind">{item.kind}</span>
										{#each item.tags.slice(0, 3) as tag}
											<span class="item-tag">#{tag}</span>
										{/each}
									</span>
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</BorgPanel>

			<div class="detail-area">
				{#if selectedItem?.source === 'note'}
					<NoteEditor
						noteId={Number(selectedItem.ref)}
						onsaved={onNoteSaved}
						onarchived={onNoteArchived}
						onnavigate={onBacklinkNavigate}
					/>
				{:else if selectedItem}
					<BrainItemPanel item={selectedItem} onclose={() => selectItem(null)} />
				{:else}
					<BorgPanel class="empty-detail-panel">
						<div class="editor-empty">
							<p>Select an item — notes open in the editor, vault &amp; actions in the reader.</p>
							<p class="hint">Use [[Note Title]] syntax to create links between notes.</p>
						</div>
					</BorgPanel>
				{/if}
			</div>
		</div>
	{:else}
		<div class="graph-layout">
			<BrainGraphView
				{sourceEnabled}
				{query}
				selectedId={selectedItem?.id ?? null}
				onselect={(item) => selectItem(item)}
			/>
			{#if selectedItem}
				<div class="graph-detail-wrap">
					<BrainItemPanel item={selectedItem} onclose={() => selectItem(null)} />
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.workspace {
		display: flex;
		flex-direction: column;
		gap: 16px;
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

	/* Toolbar */
	.toolbar {
		display: flex;
		gap: 12px;
		align-items: center;
		flex-wrap: wrap;
	}

	.search-box {
		flex: 1;
		min-width: 200px;
		max-width: 340px;
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
		flex-shrink: 0;
	}

	.view-toggle {
		display: flex;
		border: 1px solid var(--borg-border);
	}

	.view-tab {
		background: none;
		border: none;
		border-right: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		padding: 7px 14px;
		cursor: pointer;
		letter-spacing: 0.08em;
		transition: all 150ms ease-out;
	}

	.view-tab:last-child {
		border-right: none;
	}

	.view-tab--active {
		background-color: rgba(0, 229, 255, 0.1);
		color: var(--borg-cyan);
	}

	.insights-toggle {
		background: none;
		border: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		padding: 7px 14px;
		cursor: pointer;
		letter-spacing: 0.08em;
		transition: all 150ms ease-out;
	}

	.insights-toggle--active {
		background-color: rgba(0, 229, 255, 0.1);
		color: var(--borg-cyan);
		border-color: var(--borg-cyan);
	}

	.vault-strip {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-left: auto;
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.vault-strip a {
		color: var(--borg-cyan);
		text-decoration: none;
		border: 1px solid var(--borg-border);
		padding: 5px 10px;
		transition: border-color 120ms ease-out;
	}

	.vault-strip a:hover {
		border-color: var(--borg-cyan);
	}

	/* List view */
	.list-layout {
		display: flex;
		gap: 16px;
		min-height: 520px;
		align-items: stretch;
	}

	:global(.item-list-panel) {
		width: 340px;
		min-width: 300px;
		display: flex;
		flex-direction: column;
	}

	.item-list-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 12px 16px;
		border-bottom: 1px solid var(--borg-border);
	}

	.item-count {
		font-size: 10px;
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-text-secondary);
		letter-spacing: 0.05em;
	}

	.item-list {
		list-style: none;
		padding: 4px 0;
		margin: 0;
		flex: 1;
		overflow-y: auto;
		max-height: 640px;
	}

	.item-row {
		display: flex;
		flex-direction: column;
		gap: 4px;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		border-left: 2px solid transparent;
		padding: 10px 14px;
		cursor: pointer;
		transition: all 120ms ease-out;
	}

	.item-row:hover {
		background: var(--borg-grid);
	}

	.item-row--selected {
		border-left-color: var(--chip);
		background: var(--borg-grid);
	}

	.item-row-head {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		min-width: 0;
	}

	.item-title {
		color: var(--borg-text-primary);
		font-size: 13px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		flex: 1;
	}

	.item-date {
		font-size: 10px;
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		flex-shrink: 0;
	}

	.item-row-meta {
		display: flex;
		align-items: center;
		gap: 8px;
		padding-left: 16px;
		font-size: 10px;
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
	}

	.item-kind {
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.item-tag {
		color: var(--borg-cyan);
		opacity: 0.8;
	}

	.detail-area {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.detail-area > :global(*) {
		flex: 1;
	}

	:global(.empty-detail-panel) {
		display: flex;
	}

	.editor-empty {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		color: var(--borg-text-secondary);
		gap: 8px;
		font-size: 13px;
		padding: 48px;
	}

	.hint {
		font-size: 11px;
		color: var(--borg-text-disabled);
	}

	/* Graph view */
	.graph-layout {
		display: flex;
		gap: 16px;
		align-items: stretch;
	}

	.graph-detail-wrap {
		width: 380px;
		min-width: 380px;
		max-height: 700px;
		overflow-y: auto;
	}

	.loading-text {
		padding: 24px 16px;
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
