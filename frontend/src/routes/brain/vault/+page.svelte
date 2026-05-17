<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import {
		listDrafts,
		getDraft,
		expireDraft,
		getHabits,
		searchVault,
		getHeartbeatStatus,
	} from '$lib/api/vault';
	import type { Draft, Habit, SearchResult, HeartbeatState } from '$lib/api/vault';

	// ── State ──────────────────────────────────────────────────────────────────
	let drafts = $state<Draft[]>([]);
	let habits = $state<Habit[]>([]);
	let heartbeat = $state<HeartbeatState | null>(null);
	let searchResults = $state<SearchResult[]>([]);
	let selectedDraft = $state<{ filename: string; content: string } | null>(null);
	let searchQuery = $state('');
	let loadingDrafts = $state(true);
	let loadingHabits = $state(true);
	let loadingSearch = $state(false);
	let expiringDraft = $state<string | null>(null);
	let error = $state('');

	// ── Load ───────────────────────────────────────────────────────────────────
	async function loadAll() {
		await Promise.all([loadDrafts(), loadHabits(), loadHeartbeat()]);
	}

	async function loadDrafts() {
		loadingDrafts = true;
		try {
			drafts = await listDrafts();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load drafts';
		} finally {
			loadingDrafts = false;
		}
	}

	async function loadHabits() {
		loadingHabits = true;
		try {
			habits = await getHabits();
		} catch {
			habits = [];
		} finally {
			loadingHabits = false;
		}
	}

	async function loadHeartbeat() {
		heartbeat = await getHeartbeatStatus();
	}

	async function openDraft(filename: string) {
		try {
			const result = await getDraft(filename);
			selectedDraft = { filename, content: result.content };
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load draft';
		}
	}

	async function handleExpire(filename: string) {
		expiringDraft = filename;
		try {
			await expireDraft(filename);
			if (selectedDraft?.filename === filename) selectedDraft = null;
			await loadDrafts();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to expire draft';
		} finally {
			expiringDraft = null;
		}
	}

	async function handleSearch() {
		if (!searchQuery.trim()) return;
		loadingSearch = true;
		try {
			searchResults = await searchVault(searchQuery.trim(), 8);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Search failed';
		} finally {
			loadingSearch = false;
		}
	}

	function habitsDone(): number {
		return habits.filter((h) => h.checked).length;
	}

	function typeColor(type: string): string {
		const map: Record<string, string> = {
			'jira-triage': 'var(--borg-cyan)',
			'teams-reply': 'var(--borg-green)',
			'gitlab-summary': '#ff9800',
			general: 'var(--borg-text-secondary)',
		};
		return map[type] ?? 'var(--borg-text-secondary)';
	}

	function relativeTime(iso: string): string {
		if (!iso) return '';
		try {
			const diff = Date.now() - new Date(iso).getTime();
			const h = Math.floor(diff / 3600000);
			if (h < 1) return 'just now';
			if (h < 24) return `${h}h ago`;
			return `${Math.floor(h / 24)}d ago`;
		} catch {
			return '';
		}
	}

	onMount(loadAll);
</script>

<div class="vault-page">
	<!-- Header -->
	<div class="vault-header">
		<h1 class="vault-title">◈ VAULT</h1>
		<p class="vault-subtitle">Second Brain — Active Drafts · Habits · Search</p>
		{#if heartbeat}
			<div class="heartbeat-badge">
				<span class="hb-dot"></span>
				Last heartbeat: {relativeTime(heartbeat.timestamp)}
				· Jira: {heartbeat.jira_count} · Teams: {heartbeat.teams_count}
			</div>
		{/if}
	</div>

	{#if error}
		<div class="vault-error">{error} <button onclick={() => (error = '')}>×</button></div>
	{/if}

	<div class="vault-grid">
		<!-- LEFT: Drafts list -->
		<div class="vault-col vault-col--drafts">
			<BorgPanel>
				{#snippet header()}
					<div class="panel-head">
						<span>ACTIVE DRAFTS</span>
						<span class="panel-count">{drafts.length}</span>
					</div>
				{/snippet}

				{#if loadingDrafts}
					<p class="vault-muted">Loading drafts…</p>
				{:else if drafts.length === 0}
					<p class="vault-muted">No active drafts — heartbeat will generate them.</p>
				{:else}
					<ul class="draft-list">
						{#each drafts as draft}
							<li
								class="draft-item"
								class:draft-item--active={selectedDraft?.filename === draft.filename}
								role="button"
								tabindex="0"
								onclick={() => openDraft(draft.filename)}
								onkeydown={(e) => e.key === 'Enter' && openDraft(draft.filename)}
							>
								<div class="draft-meta">
									<span class="draft-type" style:color={typeColor(draft.type)}>
										{draft.type}
									</span>
									<span class="draft-time">{relativeTime(draft.created)}</span>
								</div>
								<p class="draft-subject">{draft.subject || draft.filename}</p>
								{#if draft.source_id}
									<span class="draft-source">{draft.source_id}</span>
								{/if}
								<p class="draft-preview">{draft.content_preview}</p>
							</li>
						{/each}
					</ul>
				{/if}
			</BorgPanel>

			<!-- Habits -->
			<BorgPanel>
				{#snippet header()}
					<div class="panel-head">
						<span>TODAY'S HABITS</span>
						<span class="panel-count">{habitsDone()}/{habits.length}</span>
					</div>
				{/snippet}

				{#if loadingHabits}
					<p class="vault-muted">Loading…</p>
				{:else if habits.length === 0}
					<p class="vault-muted">No habits configured — check ~/Memory/HABITS.md</p>
				{:else}
					<ul class="habit-list">
						{#each habits as habit}
							<li class="habit-item">
								<span class="habit-check" class:habit-check--done={habit.checked}>
									{habit.checked ? '◉' : '○'}
								</span>
								<div class="habit-body">
									<span class="habit-pillar" class:habit-pillar--done={habit.checked}>
										{habit.pillar}
									</span>
									{#if habit.description}
										<p class="habit-desc">{habit.description}</p>
									{/if}
								</div>
								{#if habit.auto_detectable}
									<BorgBadge>auto</BorgBadge>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</BorgPanel>
		</div>

		<!-- RIGHT: Draft viewer + Search -->
		<div class="vault-col vault-col--main">
			<!-- Draft viewer -->
			{#if selectedDraft}
				<BorgPanel>
					{#snippet header()}
						<div class="panel-head">
							<span>{selectedDraft.filename}</span>
							<div class="draft-actions">
								<BorgButton
									variant="ghost"
									size="sm"
									disabled={expiringDraft === selectedDraft.filename}
									onclick={() => handleExpire(selectedDraft!.filename)}
								>
									{expiringDraft === selectedDraft.filename ? 'Expiring…' : 'Expire Draft'}
								</BorgButton>
								<BorgButton variant="ghost" size="sm" onclick={() => (selectedDraft = null)}>
									Close
								</BorgButton>
							</div>
						</div>
					{/snippet}

					<pre class="draft-content">{selectedDraft.content}</pre>
				</BorgPanel>
			{/if}

			<!-- Vault Search -->
			<BorgPanel>
				{#snippet header()}
					<span>VAULT SEARCH (RAG)</span>
				{/snippet}

				<div class="search-bar">
					<BorgInput
						bind:value={searchQuery}
						placeholder="Search memory vault…"
						onkeydown={(e: KeyboardEvent) => e.key === 'Enter' && handleSearch()}
					/>
					<BorgButton onclick={handleSearch} disabled={loadingSearch}>
						{loadingSearch ? 'Searching…' : 'Search'}
					</BorgButton>
				</div>

				{#if searchResults.length > 0}
					<ul class="search-results">
						{#each searchResults as result}
							<li class="search-result">
								<div class="result-meta">
									<span class="result-path">{result.path}</span>
									<span class="result-score">{result.score.toFixed(3)}</span>
								</div>
								<p class="result-content">{result.content}</p>
							</li>
						{/each}
					</ul>
				{:else if !loadingSearch && searchQuery}
					<p class="vault-muted">No results for "{searchQuery}"</p>
				{:else if !loadingSearch}
					<p class="vault-muted">
						Hybrid search across all vault notes (vector + keyword, 0.7/0.3 blend).
					</p>
				{/if}
			</BorgPanel>
		</div>
	</div>
</div>

<style>
	.vault-page {
		padding: 24px;
		max-width: 1400px;
	}

	.vault-header {
		margin-bottom: 24px;
	}

	.vault-title {
		font-family: 'Share Tech Mono', monospace;
		font-size: 22px;
		color: var(--borg-cyan);
		letter-spacing: 0.12em;
		margin: 0 0 4px;
	}

	.vault-subtitle {
		font-size: 12px;
		color: var(--borg-text-secondary);
		margin: 0 0 10px;
		letter-spacing: 0.06em;
	}

	.heartbeat-badge {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-size: 11px;
		color: var(--borg-text-secondary);
		background: rgba(0, 229, 255, 0.05);
		border: 1px solid var(--borg-border);
		padding: 4px 10px;
		font-family: 'JetBrains Mono', monospace;
	}

	.hb-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--borg-green);
		animation: pulse 2s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.3; }
	}

	.vault-error {
		background: rgba(255, 50, 50, 0.1);
		border: 1px solid rgba(255, 50, 50, 0.3);
		color: #ff6b6b;
		padding: 8px 12px;
		font-size: 13px;
		margin-bottom: 16px;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.vault-error button {
		background: none;
		border: none;
		color: #ff6b6b;
		cursor: pointer;
		font-size: 16px;
	}

	.vault-grid {
		display: grid;
		grid-template-columns: 340px 1fr;
		gap: 16px;
		align-items: start;
	}

	.vault-col {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
	}

	.panel-count {
		font-size: 12px;
		color: var(--borg-cyan);
		background: rgba(0, 229, 255, 0.1);
		padding: 2px 8px;
		font-family: 'JetBrains Mono', monospace;
	}

	.vault-muted {
		color: var(--borg-text-secondary);
		font-size: 12px;
		font-style: italic;
		padding: 8px 0;
	}

	/* Draft list */
	.draft-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.draft-item {
		padding: 10px 12px;
		border: 1px solid transparent;
		border-left: 2px solid transparent;
		cursor: pointer;
		transition: all 100ms ease-out;
	}

	.draft-item:hover {
		border-color: var(--borg-border);
		border-left-color: var(--borg-cyan);
		background: rgba(0, 229, 255, 0.03);
	}

	.draft-item--active {
		border-color: var(--borg-border);
		border-left-color: var(--borg-cyan);
		background: rgba(0, 229, 255, 0.06);
	}

	.draft-meta {
		display: flex;
		justify-content: space-between;
		font-size: 10px;
		margin-bottom: 4px;
		font-family: 'JetBrains Mono', monospace;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.draft-time {
		color: var(--borg-text-secondary);
	}

	.draft-subject {
		font-size: 13px;
		color: var(--borg-text-primary);
		margin: 0 0 3px;
		font-weight: 500;
	}

	.draft-source {
		font-size: 10px;
		color: var(--borg-cyan);
		font-family: 'JetBrains Mono', monospace;
		opacity: 0.7;
	}

	.draft-preview {
		font-size: 11px;
		color: var(--borg-text-secondary);
		margin: 4px 0 0;
		overflow: hidden;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
	}

	/* Draft viewer */
	.draft-actions {
		display: flex;
		gap: 8px;
	}

	.draft-content {
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		color: var(--borg-text-primary);
		white-space: pre-wrap;
		word-break: break-word;
		line-height: 1.6;
		margin: 0;
		max-height: 500px;
		overflow-y: auto;
	}

	/* Habits */
	.habit-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.habit-item {
		display: flex;
		align-items: flex-start;
		gap: 10px;
	}

	.habit-check {
		font-size: 16px;
		color: var(--borg-text-secondary);
		line-height: 1.4;
		flex-shrink: 0;
	}

	.habit-check--done {
		color: var(--borg-green);
	}

	.habit-body {
		flex: 1;
	}

	.habit-pillar {
		font-size: 13px;
		font-weight: 600;
		color: var(--borg-text-primary);
	}

	.habit-pillar--done {
		color: var(--borg-text-secondary);
		text-decoration: line-through;
	}

	.habit-desc {
		font-size: 11px;
		color: var(--borg-text-secondary);
		margin: 2px 0 0;
	}

	/* Search */
	.search-bar {
		display: flex;
		gap: 8px;
		margin-bottom: 16px;
	}

	.search-results {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.search-result {
		border-left: 2px solid var(--borg-border-active);
		padding-left: 12px;
	}

	.result-meta {
		display: flex;
		justify-content: space-between;
		margin-bottom: 4px;
	}

	.result-path {
		font-size: 11px;
		color: var(--borg-cyan);
		font-family: 'JetBrains Mono', monospace;
	}

	.result-score {
		font-size: 10px;
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
	}

	.result-content {
		font-size: 12px;
		color: var(--borg-text-primary);
		margin: 0;
		line-height: 1.5;
	}
</style>
