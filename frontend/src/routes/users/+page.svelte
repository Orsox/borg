<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import { currentUser } from '$lib/stores/auth';
	import {
		listUsers,
		createUser,
		updateUserUsername,
		adminSetPassword,
		deactivateUser,
	} from '$lib/api/users';
	import type { UserListItem } from '$lib/api/users';

	let users = $state<UserListItem[]>([]);
	let selectedUser: UserListItem | null = $state(null);
	let showCreateForm = $state(false);
	let loading = $state(true);
	let error = $state('');

	// Create form
	let newUsername = $state('');
	let newPassword = $state('');
	let newIsAdmin = $state(false);
	let saving = $state(false);

	// Set password form
	let setPasswordValue = $state('');
	let settingPassword = $state(false);

	// Edit username form
	let editUsername = $state('');
	let editingUsername = $state(false);

	async function loadUsers() {
		try {
			const result = await listUsers();
			users = result.items;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load users';
		} finally {
			loading = false;
		}
	}

	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = '';
		try {
			await createUser(newUsername, newPassword, newIsAdmin);
			newUsername = '';
			newPassword = '';
			newIsAdmin = false;
			showCreateForm = false;
			await loadUsers();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create user';
		} finally {
			saving = false;
		}
	}

	async function handleSetPassword(e: SubmitEvent) {
		e.preventDefault();
		if (!selectedUser) return;
		settingPassword = true;
		error = '';
		try {
			await adminSetPassword(selectedUser.id, setPasswordValue);
			setPasswordValue = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to set password';
		} finally {
			settingPassword = false;
		}
	}

	async function handleEditUsername(e: SubmitEvent) {
		e.preventDefault();
		if (!selectedUser) return;
		editingUsername = true;
		error = '';
		try {
			await updateUserUsername(selectedUser.id, editUsername);
			editUsername = '';
			await loadUsers();
			selectedUser = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to update username';
		} finally {
			editingUsername = false;
		}
	}

	async function handleDeactivate() {
		if (!selectedUser) return;
		try {
			await deactivateUser(selectedUser.id);
			selectedUser = null;
			await loadUsers();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to deactivate user';
		}
	}

	function selectUser(user: UserListItem) {
		selectedUser = user;
		editUsername = user.username;
	}

	onMount(async () => {
		// Redirect non-admins
		if ($currentUser && !$currentUser.is_admin) {
			await goto('/');
			return;
		}
		await loadUsers();
	});
</script>

<svelte:head>
	<title>BorgOS — User Management</title>
</svelte:head>

<div class="users-container">
	<header class="module-header">
		<div class="header-left">
			<h1>USER MANAGEMENT</h1>
			<p class="subtitle">Assimilated units &amp; access control</p>
		</div>
		<BorgButton
			onclick={() => { showCreateForm = !showCreateForm; }}
			variant="primary"
			class="header-btn"
		>
			{showCreateForm ? 'CANCEL' : '+ NEW UNIT'}
		</BorgButton>
	</header>

	{#if error}
		<div class="error-banner" role="alert" aria-live="polite">⚠ {error}</div>
	{/if}

	<!-- Create User Form -->
	{#if showCreateForm}
		<BorgPanel class="create-panel">
			<h2 class="panel-title">CREATE NEW UNIT</h2>
			<form onsubmit={handleCreate} class="create-form" novalidate>
				<div class="form-row">
					<div class="form-field">
						<label class="form-label">Identity</label>
						<BorgInput
							bind:value={newUsername}
							placeholder="unit-designation"
							autocomplete="username"
							disabled={saving}
						/>
					</div>
					<div class="form-field">
						<label class="form-label">Access Code</label>
						<BorgInput
							type="password"
							bind:value={newPassword}
							placeholder="••••••••"
							autocomplete="new-password"
							disabled={saving}
						/>
					</div>
				</div>
				<div class="form-field checkbox-field">
					<label class="checkbox-label">
						<input type="checkbox" bind:checked={newIsAdmin} disabled={saving} />
						<span>Grant Admin Privileges</span>
					</label>
				</div>
				<BorgButton type="submit" variant="primary" disabled={saving || !newUsername || !newPassword}>
					{saving ? 'ASSIMILATING...' : 'ASSIMILATE UNIT'}
				</BorgButton>
			</form>
		</BorgPanel>
	{/if}

	<div class="users-grid">
		<!-- User List -->
		<BorgPanel class="list-panel">
			<h2 class="panel-title">UNIT ROSTER ({users.length})</h2>
			{#if loading}
				<div class="loading">Scanning collective...</div>
			{:else}
				<div class="user-list">
					{#each users as user (user.id)}
						<div
							class="user-item {selectedUser?.id === user.id ? 'selected' : ''}"
							onclick={() => selectUser(user)}
						>
							<div class="user-info">
								<span class="user-name">{user.username}</span>
								{#if user.is_admin}
									<BorgBadge status="assimilated">ADMIN</BorgBadge>
								{/if}
								{#if !user.is_active}
									<BorgBadge status="error">INACTIVE</BorgBadge>
								{/if}
							</div>
							<span class="user-date">
								{new Date(user.created_at).toLocaleDateString()}
							</span>
						</div>
					{/each}
				</div>
			{/if}
		</BorgPanel>

		<!-- User Detail -->
		<BorgPanel class="detail-panel">
			{#if selectedUser}
				<h2 class="panel-title">UNIT DETAILS</h2>
				<div class="detail-field">
					<span class="detail-label">ID</span>
					<span class="detail-value">{selectedUser.id}</span>
				</div>
				<div class="detail-field">
					<span class="detail-label">Identity</span>
					<span class="detail-value">{selectedUser.username}</span>
				</div>
				<div class="detail-field">
					<span class="detail-label">Role</span>
					<span class="detail-value">
						{selectedUser.is_admin ? 'ADMIN' : 'STANDARD'}
					</span>
				</div>
				<div class="detail-field">
					<span class="detail-label">Status</span>
					<span class="detail-value {selectedUser.is_active ? '' : 'inactive'}">
						{selectedUser.is_active ? 'ACTIVE' : 'INACTIVE'}
					</span>
				</div>
				<div class="detail-field">
					<span class="detail-label">Assimilated</span>
					<span class="detail-value">
						{new Date(selectedUser.created_at).toLocaleString()}
					</span>
				</div>

				<div class="detail-actions">
					<!-- Edit Username -->
					<form onsubmit={handleEditUsername} class="action-form" novalidate>
						<div class="form-field">
							<label class="form-label">Edit Identity</label>
							<div class="inline-form">
								<BorgInput
									bind:value={editUsername}
									placeholder="new-identity"
									autocomplete="username"
									disabled={editingUsername}
									class="inline-input"
								/>
								<BorgButton
									type="submit"
									variant="secondary"
									disabled={editingUsername || !editUsername}
									class="inline-btn"
								>
									{editingUsername ? '...' : 'UPDATE'}
								</BorgButton>
							</div>
						</div>
					</form>

					<!-- Set Password -->
					<form onsubmit={handleSetPassword} class="action-form" novalidate>
						<div class="form-field">
							<label class="form-label">Override Access Code</label>
							<div class="inline-form">
								<BorgInput
									type="password"
									bind:value={setPasswordValue}
									placeholder="••••••••"
									autocomplete="new-password"
									disabled={settingPassword}
									class="inline-input"
								/>
								<BorgButton
									type="submit"
									variant="secondary"
									disabled={settingPassword || !setPasswordValue}
									class="inline-btn"
								>
									{settingPassword ? '...' : 'SET'}
								</BorgButton>
							</div>
						</div>
					</form>

					<!-- Deactivate -->
					{#if selectedUser.is_active}
						<BorgButton
							onclick={handleDeactivate}
							variant="danger"
							class="deactivate-btn"
						>
							DEACTIVATE UNIT
						</BorgButton>
					{/if}
				</div>
			{:else}
				<div class="empty-detail">
					<span class="empty-icon">⬡</span>
					<p>Select a unit to view details</p>
				</div>
			{/if}
		</BorgPanel>
	</div>
</div>

<style>
	.users-container {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.module-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
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

	.header-btn {
		align-self: flex-start;
	}

	.error-banner {
		color: var(--borg-red);
		font-size: 13px;
		padding: 8px 12px;
		border: 1px solid var(--borg-red);
		background-color: rgba(255, 34, 68, 0.08);
	}

	.create-panel {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.panel-title {
		font-size: 14px;
		color: var(--borg-cyan);
		letter-spacing: 0.1em;
		margin: 0 0 8px;
		padding-bottom: 8px;
		border-bottom: 1px solid var(--borg-border);
	}

	.create-form {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 16px;
	}

	.form-field {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.form-label {
		font-size: 11px;
		color: var(--borg-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.15em;
	}

	.checkbox-field {
		flex-direction: row;
		align-items: center;
	}

	.checkbox-label {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		color: var(--borg-text-primary);
		cursor: pointer;
	}

	.checkbox-label input[type="checkbox"] {
		accent-color: var(--borg-cyan);
	}

	.users-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 16px;
		min-height: 400px;
	}

	.list-panel,
	.detail-panel {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.loading {
		color: var(--borg-text-secondary);
		font-size: 13px;
		text-align: center;
		padding: 40px;
	}

	.user-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
		overflow-y: auto;
		flex: 1;
	}

	.user-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 10px 12px;
		cursor: pointer;
		border: 1px solid transparent;
		transition: all 150ms ease-out;
	}

	.user-item:hover {
		background-color: rgba(0, 229, 255, 0.04);
		border-color: var(--borg-border);
	}

	.user-item.selected {
		background-color: rgba(0, 229, 255, 0.08);
		border-color: var(--borg-cyan);
	}

	.user-info {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.user-name {
		font-size: 13px;
		color: var(--borg-text-primary);
	}

	.user-date {
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	.detail-field {
		display: flex;
		justify-content: space-between;
		font-size: 13px;
		padding: 6px 0;
		border-bottom: 1px solid var(--borg-border);
	}

	.detail-label {
		color: var(--borg-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		font-size: 11px;
	}

	.detail-value {
		color: var(--borg-text-primary);
	}

	.detail-value.inactive {
		color: var(--borg-red);
	}

	.detail-actions {
		display: flex;
		flex-direction: column;
		gap: 16px;
		margin-top: 12px;
	}

	.action-form {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.inline-form {
		display: flex;
		gap: 8px;
	}

	.inline-input {
		flex: 1;
	}

	.inline-btn {
		white-space: nowrap;
	}

	.deactivate-btn {
		align-self: flex-start;
	}

	.empty-detail {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		gap: 12px;
		color: var(--borg-text-secondary);
	}

	.empty-icon {
		font-size: 48px;
		opacity: 0.3;
	}

	.empty-detail p {
		margin: 0;
		font-size: 13px;
	}
</style>
