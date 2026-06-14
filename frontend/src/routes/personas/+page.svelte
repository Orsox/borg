<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';

	import { listPersonas, getPersona, createPersona, updatePersona, deletePersona } from '$lib/api/personas';
	import type { PersonaListItem, PersonaDetail, LlmConfig, DiscordConfig } from '$lib/api/personas';

	// ── State ────────────────────────────────────────────────────────
	let personas = $state<PersonaListItem[]>([]);
	let selectedPersona: PersonaDetail | null = $state(null);
	let showCreateForm = $state(false);
	let loading = $state(true);
	let error = $state('');
	let saving = $state(false);

	// Create form fields
	let newKey = $state('');
	let newDisplayName = $state('');
	let newColor = $state('#00e5ff');
	let newSystemPrompt = $state('');

	// Edit form state (bound to selected persona)
	let editLlm = $state<LlmConfig>({ base_url: '', model_id: '', context_window: 131072, max_tokens: 2048, temperature: 0.3 });
	let editDiscord = $state<DiscordConfig>({ enabled: false, token: null, channel_id: null, allowed_user_ids: null, prefix: '!', mention_prefix: '' });

	// ── Load ─────────────────────────────────────────────────────────
	async function loadPersonas() {
		try {
			const result = await listPersonas();
			personas = result.items;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load personas';
		} finally {
			loading = false;
		}
	}

	async function selectPersona(id: number) {
		try {
			const detail = await getPersona(id);
			selectedPersona = detail;
			editLlm = { ...detail.llm };
			editDiscord = { ...detail.discord, token: detail.discord.token || null };
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load persona details';
		}
	}

	// ── Create ───────────────────────────────────────────────────────
	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		if (!newKey || !newDisplayName) return;
		saving = true;
		error = '';
		try {
			await createPersona({
				key: newKey,
				display_name: newDisplayName,
				color: newColor || null,
				system_prompt: newSystemPrompt || null,
				is_active: true,
				include_in_meetings: true,
			});
			resetCreateForm();
			showCreateForm = false;
			await loadPersonas();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create persona';
		} finally {
			saving = false;
		}
	}

	function resetCreateForm() {
		newKey = ''; newDisplayName = ''; newColor = '#00e5ff'; newSystemPrompt = '';
	}

	// ── Update ───────────────────────────────────────────────────────
	async function handleSaveLlmConfig() {
		if (!selectedPersona) return;
		saving = true; error = '';
		try {
			selectedPersona = await updatePersona(selectedPersona.id, { llm: editLlm });
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save LLM config';
		} finally {
			saving = false;
		}
	}

	async function handleSaveDiscordConfig() {
		if (!selectedPersona) return;
		saving = true; error = '';
		try {
			selectedPersona = await updatePersona(selectedPersona.id, { discord: editDiscord });
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save Discord config';
		} finally {
			saving = false;
		}
	}

	async function handleSaveSystemPrompt() {
		if (!selectedPersona) return;
		saving = true; error = '';
		try {
			selectedPersona = await updatePersona(selectedPersona.id, { system_prompt: selectedPersona.system_prompt });
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save system prompt';
		} finally {
			saving = false;
		}
	}

	async function handleToggleActive() {
		if (!selectedPersona) return;
		try {
			selectedPersona = await updatePersona(selectedPersona.id, { is_active: !selectedPersona.is_active });
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to toggle active state';
		}
	}

	async function handleToggleMeetings() {
		if (!selectedPersona) return;
		try {
			selectedPersona = await updatePersona(selectedPersona.id, { include_in_meetings: !selectedPersona.include_in_meetings });
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to toggle meeting inclusion';
		}
	}

	async function handleDelete() {
		if (!selectedPersona) return;
		saving = true; error = '';
		try {
			await deletePersona(selectedPersona.id);
			selectedPersona = null;
			await loadPersonas();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete persona';
		} finally {
			saving = false;
		}
	}

	async function handleSaveBasicInfo() {
		if (!selectedPersona) return;
		saving = true; error = '';
		try {
			selectedPersona = await updatePersona(selectedPersona.id, {
				display_name: selectedPersona.display_name,
				color: selectedPersona.color,
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save basic info';
		} finally {
			saving = false;
		}
	}

	onMount(loadPersonas);
</script>

<svelte:head>
	<title>BorgOS — Persona Management</title>
</svelte:head>

<div class="persona-container">
	<header class="module-header">
		<h1>PERSONA MANAGEMENT</h1>
		<BorgButton onclick={() => showCreateForm = !showCreateForm} variant="primary">
			{showCreateForm ? 'CANCEL' : '+ NEW PERSONA'}
		</BorgButton>
	</header>

	{#if error}
		<div class="error-banner" role="alert">{error}</div>
	{/if}

	<!-- ── Create Form ──────────────────────────────────────────── -->
	{#if showCreateForm}
		<BorgPanel>
			<h2 class="panel-title">CREATE PERSONA</h2>
			<form onsubmit={handleCreate}>
				<div class="form-row">
					<div class="form-field">
						<label for="new-key">Key</label>
						<BorgInput id="new-key" bind:value={newKey} placeholder="my-character" />
					</div>
					<div class="form-field">
						<label for="new-name">Display Name</label>
						<BorgInput id="new-name" bind:value={newDisplayName} placeholder="My Character" />
					</div>
					<div class="form-field color-field">
						<label for="new-color">Colour</label>
						<input type="color" id="new-color" bind:value={newColor} class="colour-picker" />
					</div>
				</div>
				<div class="form-field full-width">
					<label for="new-prompt">System Prompt (initial)</label>
					<textarea id="new-prompt" bind:value={newSystemPrompt} rows="4" placeholder="Du bist ..." class="prompt-textarea"></textarea>
				</div>
				<BorgButton type="submit" variant="primary" disabled={saving || !newKey || !newDisplayName}>
					{saving ? 'CREATING...' : 'CREATE'}
				</BorgButton>
			</form>
		</BorgPanel>
	{/if}

	<!-- ── Main Content ─────────────────────────────────────────── -->
	<div class="persona-grid">
		<!-- Left: Persona List -->
		<BorgPanel>
			<h2 class="panel-title">{loading ? 'LOADING...' : `PERSONAS (${personas.length})`}</h2>
			{#if loading}
				<p class="loading-text">Scanning...</p>
			{:else if personas.length === 0}
				<p class="empty-state">No personas found. Create one above.</p>
			{:else}
				<div class="persona-list" role="list">
					{#each personas as p (p.id)}
						<button
							class="persona-row"
							class:persona-row--active={selectedPersona?.id === p.id}
							onclick={() => selectPersona(p.id)}
							role="listitem"
						>
							<div class="row-main">
								<span class="colour-dot" style="background-color: {p.color || '#555'}"></span>
								<span class="row-name">{p.display_name}</span>
								<BorgBadge status={p.is_active ? 'online' : 'idle'}>{p.is_active ? 'ACTIVE' : 'INACTIVE'}</BorgBadge>
							</div>
							<div class="row-meta">
								<span class="row-key">{p.key}</span>
								{#if p.discord_enabled}
									<span class="discord-badge">DISCORD</span>
								{/if}
							</div>
						</button>
					{/each}
				</div>
			{/if}
		</BorgPanel>

		<!-- Right: Detail Panel -->
		<BorgPanel class="detail-panel">
			{#if selectedPersona}
				<div class="detail-content">
					<header class="detail-header">
						<div class="header-title">
							<span class="colour-dot large" style="background-color: {selectedPersona.color || '#555'}"></span>
							<input type="text" value={selectedPersona.display_name}
								onchange={(e) => { const t = e.target as HTMLInputElement; selectedPersona = {...selectedPersona, display_name: t.value} as PersonaDetail; }}
								class="editable-name" />
						</div>
						<div class="header-actions">
							<BorgButton variant="ghost" onclick={handleToggleActive}>
								{selectedPersona.is_active ? 'DEACTIVATE' : 'ACTIVATE'}
							</BorgButton>
							<BorgButton variant="danger" onclick={handleDelete} disabled={saving}>
								DELETE
							</BorgButton>
						</div>
					</header>

					<div class="detail-meta">
						<span class="meta-item"><strong>Key:</strong> {selectedPersona.key}</span>
						<span class="meta-item"><strong>ID:</strong> {selectedPersona.id}</span>
						<BorgBadge status={selectedPersona.include_in_meetings ? 'online' : 'idle'}>
							{selectedPersona.include_in_meetings ? 'IN MEETINGS' : 'EXCLUDED FROM MEETINGS'}
						</BorgBadge>
						<button class="toggle-meeting-btn" onclick={handleToggleMeetings}>
							{selectedPersona.include_in_meetings ? 'Exclude from meetings' : 'Include in meetings'}
						</button>
					</div>

					<!-- LLM Config Section -->
					<section class="config-section">
						<h3 class="section-title">LLM CONFIGURATION</h3>
						<div class="config-grid">
							<div class="form-field">
								<label>Base URL</label>
								<BorgInput type="text" bind:value={editLlm.base_url} placeholder="http://localhost:1234/v1" />
							</div>
							<div class="form-field">
								<label>Model ID</label>
								<BorgInput type="text" bind:value={editLlm.model_id} placeholder="qwen/qwen3.6-35b-a3b-mtp" />
							</div>
							<div class="form-field number-field">
								<label>Context Window</label>
								<BorgInput type="number" value={String(editLlm.context_window)}
									oninput={(e) => { const t = e.target as HTMLInputElement; editLlm = {...editLlm, context_window: parseInt(t.value) || 131072}; }} />
							</div>
							<div class="form-field number-field">
								<label>Max Tokens</label>
								<BorgInput type="number" value={String(editLlm.max_tokens)}
									oninput={(e) => { const t = e.target as HTMLInputElement; editLlm = {...editLlm, max_tokens: parseInt(t.value) || 2048}; }} />
							</div>
							<div class="form-field number-field">
								<label>Temperature</label>
								<BorgInput type="number" value={String(editLlm.temperature)}
									oninput={(e) => { const t = e.target as HTMLInputElement; editLlm = {...editLlm, temperature: parseFloat(t.value) || 0.3}; }} />
							</div>
						</div>
						<BorgButton variant="primary" onclick={handleSaveLlmConfig} disabled={saving}>SAVE LLM CONFIG</BorgButton>
					</section>

					<!-- Discord Config Section -->
					<section class="config-section">
						<h3 class="section-title">DISCORD BOT ACCOUNT</h3>
						<div class="form-field checkbox-field">
							<label>
								<input type="checkbox" bind:checked={editDiscord.enabled} />
								Discord bot enabled
							</label>
						</div>
						{#if editDiscord.enabled}
							<div class="config-grid">
								<div class="form-field">
									<label>Bot Token</label>
									<BorgInput type="password" value={editDiscord.token || ''}
								oninput={(e) => { const t = e.target as HTMLInputElement; editDiscord = {...editDiscord, token: t.value || null}; }}
								placeholder="Enter bot token..." autocomplete="new-password" />
								</div>
								<div class="form-field number-field">
									<label>Channel ID</label>
									<BorgInput type="number" value={String(editDiscord.channel_id ?? '')}
										oninput={(e) => { const t = e.target as HTMLInputElement; editDiscord = {...editDiscord, channel_id: parseInt(t.value) || null}; }} />
								</div>
								<div class="form-field">
									<label>Allowed User IDs</label>
									<BorgInput type="text" value={editDiscord.allowed_user_ids || ''}
								oninput={(e) => { const t = e.target as HTMLInputElement; editDiscord = {...editDiscord, allowed_user_ids: t.value || null}; }}
								placeholder="123,456 (comma-separated)" />
								</div>
								<div class="form-field">
									<label>Prefix</label>
									<BorgInput type="text" bind:value={editDiscord.prefix} />
								</div>
								<div class="form-field">
									<label>Mention Prefix</label>
									<BorgInput type="text" bind:value={editDiscord.mention_prefix} placeholder="@Locutus" />
								</div>
							</div>
						{/if}
						<BorgButton variant="primary" onclick={handleSaveDiscordConfig} disabled={saving}>SAVE DISCORD CONFIG</BorgButton>
					</section>

					<!-- System Prompt Section -->
					<section class="config-section">
						<h3 class="section-title">SYSTEM PROMPT</h3>
						<textarea bind:value={selectedPersona.system_prompt} rows="12" placeholder="Enter system prompt..." class="prompt-textarea full-width"></textarea>
						<BorgButton variant="primary" onclick={handleSaveSystemPrompt} disabled={saving}>SAVE SYSTEM PROMPT</BorgButton>
					</section>
				</div>
			{:else}
				<div class="empty-detail">
					<p>Select a persona to view details</p>
				</div>
			{/if}
		</BorgPanel>
	</div>
</div>

<style>
	.persona-container { display: flex; flex-direction: column; gap: 16px; }

	.module-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
	.module-header h1 { font-size: 24px; color: var(--borg-cyan); letter-spacing: 0.15em; margin: 0; }

	.error-banner { border: 1px solid var(--borg-red); color: var(--borg-red); padding: 8px 12px; font-size: 13px; }
	.loading-text, .empty-state { color: var(--borg-text-secondary); font-style: italic; margin-top: 8px; }

	/* Create form */
	.form-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end; margin-bottom: 12px; }
	.form-field { display: flex; flex-direction: column; gap: 4px; }
	.form-field label { font-size: 11px; color: var(--borg-text-secondary); text-transform: uppercase; letter-spacing: 0.08em; }
	.full-width { grid-column: 1 / -1; }
	.prompt-textarea { width: 100%; background: var(--borg-void-bg); border: 1px solid var(--borg-border); color: var(--borg-text-primary); font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 8px; resize: vertical; }
	.colour-picker { width: 40px; height: 32px; border: 1px solid var(--borg-border); background: none; cursor: pointer; }

	/* Grid layout */
	.persona-grid { display: grid; grid-template-columns: 380px 1fr; gap: 16px; min-height: 500px; }

	/* Persona list */
	.panel-title { font-size: 14px; color: var(--borg-cyan); letter-spacing: 0.1em; margin: 0 0 8px; padding-bottom: 8px; border-bottom: 1px solid var(--borg-border); }

	.persona-list { display: flex; flex-direction: column; gap: 2px; max-height: calc(100vh - 350px); overflow-y: auto; }
	.persona-row { background: none; border: none; cursor: pointer; padding: 8px 10px; text-align: left; display: flex; flex-direction: column; gap: 4px; border-left: 2px solid transparent; transition: all 150ms ease; }
	.persona-row:hover { background-color: rgba(0, 229, 255, 0.04); border-left-color: var(--borg-border-active); }
	.persona-row--active { border-left-color: var(--borg-cyan); background-color: rgba(0, 229, 255, 0.06); }

	.row-main { display: flex; align-items: center; gap: 8px; }
	.colour-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
	.colour-dot.large { width: 14px; height: 14px; }
	.row-name { font-size: 13px; color: var(--borg-text-primary); font-weight: 600; }
	.row-meta { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--borg-text-secondary); }
	.discord-badge { background: rgba(88, 101, 242, 0.2); color: #7289da; padding: 1px 6px; border-radius: 3px; font-size: 10px; letter-spacing: 0.05em; }

	/* Detail panel */
	.detail-panel { overflow-y: auto; max-height: calc(100vh - 200px); }
	.empty-detail { display: flex; align-items: center; justify-content: center; height: 300px; color: var(--borg-text-secondary); font-style: italic; }

	.detail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--borg-border); }
	.header-title { display: flex; align-items: center; gap: 10px; }
	.editable-name { font-size: 18px; color: var(--borg-cyan); background: none; border: none; font-family: 'Share Tech Mono', monospace; letter-spacing: 0.05em; width: 200px; }

	.detail-meta { display: flex; gap: 16px; align-items: center; margin-bottom: 20px; font-size: 12px; color: var(--borg-text-secondary); flex-wrap: wrap; }
	.meta-item strong { color: var(--borg-text-primary); }
	.toggle-meeting-btn { background: none; border: 1px solid var(--borg-border); color: var(--borg-text-secondary); font-size: 11px; padding: 3px 8px; cursor: pointer; text-transform: uppercase; letter-spacing: 0.05em; }
	.toggle-meeting-btn:hover { border-color: var(--borg-cyan); color: var(--borg-cyan); }

	/* Config sections */
	.config-section { margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--borg-border); }
	.section-title { font-size: 13px; color: var(--borg-cyan); letter-spacing: 0.1em; margin: 0 0 12px; }
	.config-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 12px; }
	.checkbox-field label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px !important; text-transform: none !important; color: var(--borg-text-primary) !important; }

	/* Responsive */
	@media (max-width: 900px) {
		.persona-grid { grid-template-columns: 1fr; }
		.form-row { grid-template-columns: 1fr 1fr; }
	}
</style>
