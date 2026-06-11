<script lang="ts">
	import { goto } from '$app/navigation';
	import { sourceColor, sourceLabel } from './BrainItemPanel.svelte';
	import { searchBrain, type BrainSearchResult } from '$lib/api/brain';

	let open = $state(false);
	let query = $state('');
	let results = $state<BrainSearchResult[]>([]);
	let activeIndex = $state(0);
	let searching = $state(false);
	let searchError = $state('');
	let inputEl = $state<HTMLInputElement>();
	let listEl = $state<HTMLDivElement>();

	let debounceTimer: ReturnType<typeof setTimeout> | undefined;
	let searchSeq = 0;

	export function show() {
		open = true;
		query = '';
		results = [];
		activeIndex = 0;
		searchError = '';
		setTimeout(() => inputEl?.focus(), 0);
	}

	function close() {
		open = false;
		clearTimeout(debounceTimer);
	}

	$effect(() => {
		const q = query.trim();
		clearTimeout(debounceTimer);
		if (!open || q.length < 2) {
			results = [];
			activeIndex = 0;
			return;
		}
		debounceTimer = setTimeout(() => runSearch(q), 200);
		return () => clearTimeout(debounceTimer);
	});

	async function runSearch(q: string) {
		const seq = ++searchSeq;
		searching = true;
		searchError = '';
		try {
			const r = await searchBrain(q, undefined, 15);
			if (seq !== searchSeq) return; // stale response
			results = r.results;
			activeIndex = 0;
		} catch (e) {
			if (seq !== searchSeq) return;
			searchError = e instanceof Error ? e.message : 'Search failed';
			results = [];
		} finally {
			if (seq === searchSeq) searching = false;
		}
	}

	function openResult(r: BrainSearchResult) {
		close();
		goto(`/brain?item=${encodeURIComponent(r.id)}`);
	}

	function onWindowKeydown(ev: KeyboardEvent) {
		if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
			ev.preventDefault();
			open ? close() : show();
			return;
		}
		if (!open) return;
		if (ev.key === 'Escape') {
			ev.preventDefault();
			close();
		} else if (ev.key === 'ArrowDown') {
			ev.preventDefault();
			if (results.length) activeIndex = (activeIndex + 1) % results.length;
			scrollActiveIntoView();
		} else if (ev.key === 'ArrowUp') {
			ev.preventDefault();
			if (results.length) activeIndex = (activeIndex - 1 + results.length) % results.length;
			scrollActiveIntoView();
		} else if (ev.key === 'Enter') {
			ev.preventDefault();
			const r = results[activeIndex];
			if (r) openResult(r);
		}
	}

	function scrollActiveIntoView() {
		setTimeout(() => {
			listEl?.querySelector('.palette-row--active')?.scrollIntoView({ block: 'nearest' });
		}, 0);
	}
</script>

<svelte:window onkeydown={onWindowKeydown} />

{#if open}
	<div
		class="palette-backdrop"
		role="presentation"
		onpointerdown={(ev) => {
			if (ev.target === ev.currentTarget) close();
		}}
	>
		<div class="palette" role="dialog" aria-modal="true" aria-label="Search the second brain">
			<div class="palette-input-row">
				<span class="palette-glyph" aria-hidden="true">◉</span>
				<input
					bind:this={inputEl}
					bind:value={query}
					class="palette-input"
					placeholder="Search notes, vault, actions…"
					autocomplete="off"
					spellcheck="false"
				/>
				<kbd class="palette-kbd">ESC</kbd>
			</div>

			<div class="palette-results" bind:this={listEl}>
				{#if query.trim().length < 2}
					<p class="palette-status">Type to search across all memory sources.</p>
				{:else if searching && results.length === 0}
					<p class="palette-status">SEARCHING…</p>
				{:else if searchError}
					<p class="palette-status palette-status--error">{searchError}</p>
				{:else if results.length === 0}
					<p class="palette-status">No matches.</p>
				{:else}
					{#each results as r, i (r.id)}
						<button
							type="button"
							class="palette-row"
							class:palette-row--active={i === activeIndex}
							style:--chip={sourceColor[r.source]}
							onclick={() => openResult(r)}
							onmouseenter={() => (activeIndex = i)}
						>
							<span class="chip-dot"></span>
							<span class="palette-title">{r.title}</span>
							<span class="palette-source">{sourceLabel[r.source]}</span>
						</button>
					{/each}
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.palette-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		z-index: 200;
		display: flex;
		justify-content: center;
		padding-top: 14vh;
	}

	.palette {
		width: min(620px, 92vw);
		height: fit-content;
		max-height: 60vh;
		display: flex;
		flex-direction: column;
		background: var(--borg-void);
		border: 1px solid var(--borg-cyan);
		box-shadow: 0 0 32px rgba(0, 229, 255, 0.15), 0 16px 48px rgba(0, 0, 0, 0.7);
	}

	.palette-input-row {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 16px;
		border-bottom: 1px solid var(--borg-border);
	}

	.palette-glyph {
		color: var(--borg-cyan);
		font-size: 14px;
	}

	.palette-input {
		flex: 1;
		background: none;
		border: none;
		outline: none;
		color: var(--borg-text-primary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 14px;
	}

	.palette-input::placeholder {
		color: var(--borg-text-disabled);
	}

	.palette-kbd {
		font-family: 'JetBrains Mono', monospace;
		font-size: 9px;
		color: var(--borg-text-secondary);
		border: 1px solid var(--borg-border);
		padding: 2px 6px;
		letter-spacing: 0.05em;
	}

	.palette-results {
		overflow-y: auto;
	}

	.palette-status {
		margin: 0;
		padding: 16px;
		font-size: 11px;
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-text-secondary);
		letter-spacing: 0.05em;
	}

	.palette-status--error {
		color: var(--borg-red);
	}

	.palette-row {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		border-left: 2px solid transparent;
		padding: 10px 16px;
		cursor: pointer;
	}

	.palette-row--active {
		background: rgba(0, 229, 255, 0.08);
		border-left-color: var(--chip);
	}

	.chip-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--chip);
		flex-shrink: 0;
	}

	.palette-title {
		flex: 1;
		font-size: 13px;
		color: var(--borg-text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.palette-source {
		font-size: 9px;
		font-family: 'JetBrains Mono', monospace;
		color: var(--borg-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		flex-shrink: 0;
	}
</style>
