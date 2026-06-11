<script lang="ts">
	import BorgPanel from './BorgPanel.svelte';
	import BorgButton from './BorgButton.svelte';
	import BorgInput from './BorgInput.svelte';
	import { getNote, updateNote, archiveNote } from '$lib/api/brain';
	import type { Note } from '$lib/api/brain';

	let {
		noteId,
		onsaved,
		onarchived,
	}: {
		noteId: number;
		onsaved?: (note: Note) => void;
		onarchived?: (id: number) => void;
	} = $props();

	let note = $state<Note | null>(null);
	let editingTitle = $state('');
	let editingContent = $state('');
	let editingTags = $state('');
	let loading = $state(false);
	let saving = $state(false);
	let error = $state('');

	$effect(() => {
		loadNote(noteId);
	});

	async function loadNote(id: number) {
		loading = true;
		error = '';
		try {
			const n = await getNote(id);
			if (noteId !== id) return; // stale response
			note = n;
			editingTitle = n.title;
			editingContent = n.content;
			editingTags = n.tags.join(', ');
		} catch (e) {
			if (noteId !== id) return;
			error = e instanceof Error ? e.message : 'Failed to load note';
			note = null;
		} finally {
			if (noteId === id) loading = false;
		}
	}

	async function saveNote() {
		if (!note) return;
		saving = true;
		try {
			const tags = editingTags
				.split(',')
				.map((t) => t.trim().toLowerCase())
				.filter(Boolean);
			const updated = await updateNote(note.id, editingTitle, editingContent, tags);
			note = updated;
			onsaved?.(updated);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save note';
		} finally {
			saving = false;
		}
	}

	async function archiveCurrentNote() {
		if (!note) return;
		try {
			await archiveNote(note.id);
			onarchived?.(note.id);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to archive note';
		}
	}

</script>

<BorgPanel class="note-editor-panel">
	{#if error}
		<div class="editor-error" role="alert">{error}</div>
	{/if}

	{#if loading}
		<div class="loading-text">LOADING NOTE...</div>
	{:else if note}
		<div class="editor-header">
			<div class="editor-title-row">
				<BorgInput bind:value={editingTitle} placeholder="Note title..." />
			</div>
			<div class="editor-actions">
				<BorgButton variant="danger" onclick={archiveCurrentNote}>ARCHIVE</BorgButton>
				<BorgButton variant="primary" onclick={saveNote} disabled={saving}>
					{saving ? 'SAVING...' : 'SAVE'}
				</BorgButton>
			</div>
		</div>

		<div class="tags-row">
			<span class="tags-label">TAGS:</span>
			<BorgInput bind:value={editingTags} placeholder="tag1, tag2, tag3" />
		</div>

		<textarea
			class="editor-textarea"
			bind:value={editingContent}
			placeholder="Write your note here... Use [[Note Title]] to link to other notes — vault titles resolve too."
		></textarea>
	{/if}
</BorgPanel>

<style>
	:global(.note-editor-panel) {
		display: flex;
		flex-direction: column;
		min-height: 480px;
	}

	.editor-error {
		margin: 16px 16px 0;
		border: 1px solid var(--borg-red);
		color: var(--borg-red);
		padding: 8px 12px;
		font-size: 12px;
	}

	.loading-text {
		padding: 48px 16px;
		text-align: center;
		color: var(--borg-cyan);
		font-size: 12px;
		letter-spacing: 0.1em;
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
</style>
