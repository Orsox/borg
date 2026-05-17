<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import { getHealth, getMe } from '$lib/api/client';
	import { authStore, currentUser } from '$lib/stores/auth';
	import { listNotes } from '$lib/api/brain';
	import { listTasks } from '$lib/api/tasks';
	import { changeMyPassword, updateMyUsername } from '$lib/api/users';

	interface HealthData {
		status: string;
		uptime_seconds: number;
		modules: Record<string, string>;
	}

	let health: HealthData | null = $state(null);
	let noteCount = $state(0);
	let taskCount = $state(0);
	let loading = $state(true);

	// Account management state
	let newUsername = $state('');
	let savingUsername = $state(false);
	let usernameError = $state('');
	let usernameSuccess = $state(false);

	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');
	let savingPassword = $state(false);
	let passwordError = $state('');
	let passwordSuccess = $state(false);

	async function loadData() {
		try {
			const [h, notes, tasks] = await Promise.all([
				getHealth(),
				listNotes(1, 1).catch(() => ({ total: 0 })),
				listTasks(1, 1).catch(() => ({ total: 0 })),
			]);
			health = h;
			noteCount = (notes as any).total ?? 0;
			taskCount = (tasks as any).total ?? 0;
		} catch {
			// Silently fail
		} finally {
			loading = false;
		}
	}

	function formatUptime(seconds: number): string {
		if (seconds < 60) return `${seconds}s`;
		if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
		if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
		return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
	}

	async function handleUsernameChange(e: SubmitEvent) {
		e.preventDefault();
		savingUsername = true;
		usernameError = '';
		usernameSuccess = false;
		try {
			await updateMyUsername(newUsername);
			const user = await getMe();
			authStore.setUser(user);
			newUsername = '';
			usernameSuccess = true;
			setTimeout(() => { usernameSuccess = false; }, 3000);
		} catch (err) {
			usernameError = err instanceof Error ? err.message : 'Failed to update';
		} finally {
			savingUsername = false;
		}
	}

	async function handlePasswordChange(e: SubmitEvent) {
		e.preventDefault();
		if (newPassword !== confirmPassword) {
			passwordError = 'New passwords do not match';
			return;
		}
		savingPassword = true;
		passwordError = '';
		passwordSuccess = false;
		try {
			await changeMyPassword(currentPassword, newPassword);
			currentPassword = '';
			newPassword = '';
			confirmPassword = '';
			passwordSuccess = true;
			setTimeout(() => { passwordSuccess = false; }, 3000);

			// Prompt browser to update stored credential
			if ('credentials' in navigator) {
				try {
					// @ts-ignore — PasswordCredential not in default TS lib
					const PasswordCred = window.PasswordCredential;
					if (PasswordCred) {
						// @ts-ignore
						const cred = new PasswordCred({
							id: $currentUser?.username ?? '',
							password: newPassword,
						});
						await navigator.credentials.store(cred);
					}
				} catch { /* optional */ }
			}
		} catch (err) {
			passwordError = err instanceof Error ? err.message : 'Failed to update';
		} finally {
			savingPassword = false;
		}
	}

	onMount(loadData);
</script>

<svelte:head>
	<title>BorgOS — Settings</title>
</svelte:head>

<div class="settings-container">
	<header class="module-header">
		<h1>SYSTEM SETTINGS</h1>
		<p class="subtitle">Configuration &amp; system status</p>
	</header>

	<div class="settings-grid">
		<!-- System Status -->
		<BorgPanel class="settings-panel">
			<h2 class="panel-title">SYSTEM STATUS</h2>
			{#if health}
				<div class="status-item">
					<span class="status-label">OVERALL</span>
					<span class="status-value status-{health.status}">{health.status.toUpperCase()}</span>
				</div>
				<div class="status-item">
					<span class="status-label">UPTIME</span>
					<span class="status-value">{formatUptime(health.uptime_seconds)}</span>
				</div>
				<div class="status-item">
					<span class="status-label">MODULES</span>
					<div class="module-status">
						{#each Object.entries(health.modules) as [name, status]}
							<span class="module-dot module-{status}">{name}: {status}</span>
						{/each}
					</div>
				</div>
			{/if}
		</BorgPanel>

		<!-- Data Overview -->
		<BorgPanel class="settings-panel">
			<h2 class="panel-title">DATA OVERVIEW</h2>
			<div class="status-item">
				<span class="status-label">NOTES</span>
				<span class="status-value">{noteCount}</span>
			</div>
			<div class="status-item">
				<span class="status-label">TASKS</span>
				<span class="status-value">{taskCount}</span>
			</div>
			<div class="status-item">
				<span class="status-label">VERSION</span>
				<span class="status-value">0.1.0</span>
			</div>
		</BorgPanel>

		<!-- Change Identity -->
		<BorgPanel class="settings-panel">
			<h2 class="panel-title">CHANGE IDENTITY</h2>
			<form onsubmit={handleUsernameChange} class="account-form" novalidate>
				<div class="form-field">
					<label class="form-label">New Identity</label>
					<BorgInput
						bind:value={newUsername}
						placeholder="new-username"
						autocomplete="username"
						disabled={savingUsername}
					/>
				</div>
				{#if usernameError}
					<div class="form-error" role="alert">⚠ {usernameError}</div>
				{/if}
				{#if usernameSuccess}
					<div class="form-success" role="status">✓ Identity updated.</div>
				{/if}
				<BorgButton type="submit" variant="primary" disabled={savingUsername || !newUsername}>
					{savingUsername ? 'UPDATING...' : 'UPDATE IDENTITY'}
				</BorgButton>
			</form>
		</BorgPanel>

		<!-- Change Access Code -->
		<BorgPanel class="settings-panel">
			<h2 class="panel-title">CHANGE ACCESS CODE</h2>
			<form onsubmit={handlePasswordChange} class="account-form" novalidate>
				<div class="form-field">
					<label class="form-label">Current Code</label>
					<BorgInput
						type="password"
						bind:value={currentPassword}
						placeholder="••••••••"
						autocomplete="current-password"
						disabled={savingPassword}
					/>
				</div>
				<div class="form-field">
					<label class="form-label">New Code</label>
					<BorgInput
						type="password"
						bind:value={newPassword}
						placeholder="••••••••"
						autocomplete="new-password"
						disabled={savingPassword}
					/>
				</div>
				<div class="form-field">
					<label class="form-label">Confirm New Code</label>
					<BorgInput
						type="password"
						bind:value={confirmPassword}
						placeholder="••••••••"
						autocomplete="new-password"
						disabled={savingPassword}
					/>
				</div>
				{#if passwordError}
					<div class="form-error" role="alert">⚠ {passwordError}</div>
				{/if}
				{#if passwordSuccess}
					<div class="form-success" role="status">✓ Access code updated.</div>
				{/if}
				<BorgButton type="submit" variant="primary" disabled={savingPassword || !currentPassword || !newPassword}>
					{savingPassword ? 'UPDATING...' : 'UPDATE CODE'}
				</BorgButton>
			</form>
		</BorgPanel>

		<!-- Keyboard Shortcuts -->
		<BorgPanel class="settings-panel">
			<h2 class="panel-title">KEYBOARD SHORTCUTS</h2>
			<div class="shortcut-list">
				<div class="shortcut-item">
					<kbd>G</kbd> + <kbd>H</kbd>
					<span>→ Archon Hub</span>
				</div>
				<div class="shortcut-item">
					<kbd>G</kbd> + <kbd>B</kbd>
					<span>→ Second Brain</span>
				</div>
				<div class="shortcut-item">
					<kbd>G</kbd> + <kbd>T</kbd>
					<span>→ Task Automation</span>
				</div>
				<div class="shortcut-item">
					<kbd>G</kbd> + <kbd>G</kbd>
					<span>→ Knowledge Graph</span>
				</div>
				<div class="shortcut-item">
					<kbd>?</kbd>
					<span>→ Toggle shortcuts</span>
				</div>
			</div>
		</BorgPanel>

		<!-- API Documentation -->
		<BorgPanel class="settings-panel">
			<h2 class="panel-title">API DOCUMENTATION</h2>
			<p class="api-info">Full API documentation is available via:</p>
			<div class="api-links">
				<a href="/api/docs" target="_blank" class="api-link">Swagger UI →</a>
				<a href="/api/redoc" target="_blank" class="api-link">ReDoc →</a>
				<a href="/api/openapi.json" target="_blank" class="api-link">OpenAPI JSON →</a>
			</div>
		</BorgPanel>
	</div>
</div>

<style>
	.settings-container {
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

	.settings-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 16px;
	}

	.settings-panel {
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

	.status-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-size: 12px;
	}

	.status-label {
		color: var(--borg-text-secondary);
		letter-spacing: 0.05em;
	}

	.status-value {
		color: var(--borg-text-primary);
	}

	.status-nominal {
		color: var(--borg-green);
	}

	.module-status {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.module-dot {
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	.module-online::before {
		content: '●';
		color: var(--borg-green);
		margin-right: 4px;
	}

	.shortcut-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.shortcut-item {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: var(--borg-text-secondary);
	}

	kbd {
		background: var(--borg-grid);
		border: 1px solid var(--borg-border);
		color: var(--borg-cyan);
		padding: 2px 6px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		min-width: 20px;
		text-align: center;
	}

	.api-info {
		font-size: 12px;
		color: var(--borg-text-secondary);
		margin: 0;
	}

	.api-links {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.api-link {
		color: var(--borg-cyan);
		font-size: 12px;
		text-decoration: none;
	}

	.api-link:hover {
		text-decoration: underline;
	}

	.account-form {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.form-error {
		color: var(--borg-red);
		font-size: 12px;
		padding: 6px 10px;
		border: 1px solid var(--borg-red);
		background-color: rgba(255, 34, 68, 0.08);
	}

	.form-success {
		color: var(--borg-green);
		font-size: 12px;
		padding: 6px 10px;
		border: 1px solid var(--borg-green);
		background-color: rgba(57, 255, 20, 0.08);
	}
</style>
