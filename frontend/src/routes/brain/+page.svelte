<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import { listNotes, createNote, getNote, updateNote, archiveNote, getBacklinks } from '$lib/api/brain';
	import type { NoteListItem, Note, BacklinkItem } from '$lib/api/brain';

	let notes = $state<NoteListItem[]>([]);
	let selectedNote: Note | null = $state(null);
	let editingTitle = $state('');
	let editingContent = $state('');
	let editingTags = $state('');
	let searchQuery = $state('');
	let showPreview = $state(false);
	let loading = $state(true);
	let saving = $state(false);
	let showBacklinks = $state(false);
	let backlinks = $state<BacklinkItem[]>([]);
	let error = $state('');

	async function loadNotes() {
		try {
			const result = await listNotes(1, 100, searchQuery || undefined);
			notes = result.items;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load notes';
		} finally {
			loading = false;
		}
	}

	async function selectNote(id: number) {
		try {
			const note = await getNote(id);
			selectedNote = note;
			editingTitle = note.title;
			editingContent = note.content;
			editingTags = note.tags.join(', ');
			showPreview = false;
			showBacklinks = false;
			backlinks = [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load note';
		}
	}

	async function newNote() {
		try {
			const note = await createNote('Untitled Note', '', []);
			await selectNote(note.id);
			await loadNotes();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create note';
		}
	}

	async function saveNote() {
		if (!selectedNote) return;
		saving = true;
		try {
			const tags = editingTags
				.split(',')
				.map((t) => t.trim().toLowerCase())
				.filter(Boolean);
			await updateNote(selectedNote.id, editingTitle, editingContent, tags);
			await selectNote(selectedNote.id);
			await loadNotes();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save note';
		} finally {
			saving = false;
		}
	}

	async function archiveSelectedNote() {
		if (!selectedNote) return;
		try {
			await archiveNote(selectedNote.id);
			selectedNote = null;
			await loadNotes();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to archive note';
		}
	}

	async function loadBacklinks() {
		if (!selectedNote) return;
		try {
			backlinks = await getBacklinks(selectedNote.id);
			showBacklinks = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load backlinks';
		}
	}

	function formatTime(dateStr: string) {
		const d = new Date(dateStr);
		return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
	}

	onMount(loadNotes);
</script>

<svelte:head>
	<title>BorgOS — Second Brain</title>
</svelte:head>

<div class="brain-container">
	<header class="module-header">
		<h1>SECOND BRAIN</h1>
		<p class="subtitle">Knowledge graph &amp; note management</p>
	</header>

	{#if error}
		<div class="error-banner" role="alert">{error}</div>
	{:else}
		<div class="brain-layout">
			<!-- Note List Sidebar -->
			<BorgPanel class="note-list-panel">
				<div class="note-list-header">
					<BorgInput
						bind:value={searchQuery}
						placeholder="Search notes..."
						on:input={loadNotes}
					/>
					<BorgButton variant="primary" onclick={newNote}>+ NEW NOTE</BorgButton>
				</div>
				{#if loading}
					<div class="loading-text">LOADING NOTES...</div>
				{:else}
					<ul class="note-list">
						{#each notes as note (note.id)}
							<li
								class="note-item {selectedNote?.id === note.id ? 'selected' : ''}"
								onclick={() => selectNote(note.id)}
							>
								<div class="note-item-title">{note.title}</div>
								<div class="note-item-meta">
									<span class="note-date">{formatTime(note.updated_at)}</span>
									{#each note.tags.slice(0, 2) as tag}
										<BorgBadge variant="cyan" size="sm">{tag}</BorgBadge>
									{/each}
									{#if note.tags.length > 2}
										<span class="more-tags">+{note.tags.length - 2}</span>
									{/if}
								</div>
							</li>
						{/each}
					</ul>
					{#if notes.length === 0}
						<div class="empty-state">No notes found. Create your first note.</div>
					{/if}
				{/if}
			</BorgPanel>

			<!-- Editor / Preview Panel -->
			<BorgPanel class="editor-panel">
				{#if selectedNote}
					<div class="editor-header">
						<div class="editor-title-row">
							<BorgInput
								bind:value={editingTitle}
								placeholder="Note title..."
								class="title-input"
							/>
						</div>
						<div class="editor-actions">
							<BorgButton
								variant={showPreview ? 'secondary' : 'primary'}
								onclick={() => showPreview = !showPreview}
							>
								{showPreview ? 'EDIT' : 'PREVIEW'}
							</BorgButton>
							<BorgButton variant="secondary" onclick={loadBacklinks}>
								{backlinks.length} BACKLINKS
							</BorgButton>
							<BorgButton variant="danger" onclick={archiveSelectedNote}>ARCHIVE</BorgButton>
							<BorgButton variant="primary" onclick={saveNote} disabled={saving}>
								{saving ? 'SAVING...' : 'SAVE'}
							</BorgButton>
						</div>
					</div>

					<div class="tags-row">
						<span class="tags-label">TAGS:</span>
						<BorgInput
							bind:value={editingTags}
							placeholder="tag1, tag2, tag3"
							class="tags-input"
						/>
					</div>

					{#if showPreview}
						<div class="preview-area" innerHTML={renderMarkdown(editingContent)}></div>
					{:else}
						<textarea
							class="editor-textarea"
							bind:value={editingContent}
							placeholder="Write your note here... Use [[Note Title]] to link to other notes."
						></textarea>
					{/if}

					{#if showBacklinks && backlinks.length}
						<div class="backlinks-section">
							<h3>BACKLINKS</h3>
							<ul>
								{#each backlinks as bl (bl.id)}
									<li onclick={() => selectNote(bl.id)}>
										<span class="backlink-title">{bl.title}</span>
										<span class="backlink-date">{formatTime(bl.updated_at)}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				{:else}
					<div class="editor-empty">
						<p>Select a note or create a new one to begin.</p>
						<p class="hint">Use [[Note Title]] syntax to create links between notes.</p>
					</div>
				{/if}
			</BorgPanel>
		</div>
	{/if}
</div>

<style>
	.brain-container {
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

	.brain-layout {
		display: flex;
		gap: 16px;
		min-height: 500px;
	}

	.note-list-panel {
		width: 320px;
		min-width: 280px;
		display: flex;
		flex-direction: column;
	}

	.note-list-header {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 16px;
	}

	.note-list {
		list-style: none;
		padding: 0 8px;
		margin: 0;
		flex: 1;
		overflow-y: auto;
	}

	.note-item {
		padding: 12px;
		margin-bottom: 4px;
		cursor: pointer;
		border-left: 2px solid transparent;
		transition: all 150ms ease-out;
	}

	.note-item:hover {
		background: var(--borg-grid);
	}

	.note-item.selected {
		border-left-color: var(--borg-cyan);
		background: var(--borg-grid);
	}

	.note-item-title {
		color: var(--borg-text-primary);
		font-size: 13px;
		margin-bottom: 4px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.note-item-meta {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	.more-tags {
		color: var(--borg-text-secondary);
		font-size: 10px;
	}

	.editor-panel {
		flex: 1;
		display: flex;
		flex-direction: column;
	}

	.editor-header {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 16px;
	}

	.editor-title-row {
		width: 100%;
	}

	.title-input {
		width: 100%;
	}

	.editor-actions {
		display: flex;
		gap: 8px;
	}

	.tags-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 0 16px 8px;
	}

	.tags-label {
		font-size: 11px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.1em;
	}

	.tags-input {
		flex: 1;
	}

	.editor-textarea {
		flex: 1;
		min-height: 300px;
		background: var(--borg-void);
		border: none;
		color: var(--borg-text-primary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 13px;
		padding: 16px;
		resize: none;
		outline: none;
		line-height: 1.6;
	}

	.editor-textarea:focus {
		box-shadow: inset 0 0 0 1px var(--borg-cyan);
	}

	.preview-area {
		flex: 1;
		min-height: 300px;
		padding: 16px;
		color: var(--borg-text-primary);
		font-size: 13px;
		line-height: 1.6;
		overflow-y: auto;
	}

	.backlinks-section {
		padding: 16px;
		border-top: 1px solid var(--borg-border);
	}

	.backlinks-section h3 {
		font-size: 12px;
		color: var(--borg-cyan);
		letter-spacing: 0.1em;
		margin: 0 0 8px;
	}

	.backlinks-section ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	.backlinks-section li {
		padding: 6px 8px;
		cursor: pointer;
		display: flex;
		justify-content: space-between;
		font-size: 12px;
		color: var(--borg-text-secondary);
	}

	.backlinks-section li:hover {
		background: var(--borg-grid);
		color: var(--borg-cyan);
	}

	.backlink-title {
		color: var(--borg-text-primary);
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
	}

	.hint {
		font-size: 11px;
		color: var(--borg-text-disabled);
	}

	.loading-text {
		padding: 16px;
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
