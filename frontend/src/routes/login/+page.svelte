<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { login } from '$lib/api/client';
	import { authStore, isAuthenticated } from '$lib/stores/auth';
	import { getMe } from '$lib/api/client';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';

	let username = $state('');
	let password = $state('');
	let errorMsg = $state('');
	let loading = $state(false);

	// Browser Credential Management API — auto-fill stored credentials
	onMount(async () => {
		if ('credentials' in navigator) {
			try {
				// @ts-ignore — PasswordCredential not in default TS lib
				const cred = await navigator.credentials.get({
					password: true,
					mediation: 'optional'
				} as any);
				// @ts-ignore
				if (cred && cred.id) {
					username = cred.id;
					// @ts-ignore
					password = cred.password ?? '';
				}
			} catch {
				// CM API not available — no-op
			}
		}
	});

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (loading) return;
		errorMsg = '';
		loading = true;

		try {
			const result = await login(username, password);
			authStore.setToken(result.access_token);
			const user = await getMe();
			authStore.setUser(user);

			// Store credential for browser password manager (Chrome/Edge/Firefox)
			if ('credentials' in navigator) {
				try {
					// @ts-ignore — PasswordCredential not in default TS lib
					const PasswordCred = window.PasswordCredential;
					if (PasswordCred) {
						// @ts-ignore
						const cred = new PasswordCred({ id: username, password });
						await navigator.credentials.store(cred);
					}
				} catch {
					// Silently ignore — CM API is optional enhancement
				}
			}

			await goto('/');
		} catch (err: unknown) {
			errorMsg = err instanceof Error ? err.message : 'Login failed';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>BorgOS — Login</title>
</svelte:head>

<div class="login-page">
	<div class="hex-bg"></div>

	<div class="login-container">
		<div class="login-header">
			<svg width="48" height="48" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
				<rect x="4" y="4" width="24" height="24" fill="none" stroke="var(--borg-cyan)" stroke-width="1.5"/>
				<rect x="8" y="8" width="6" height="6" fill="var(--borg-cyan)" opacity="0.8"/>
				<rect x="18" y="8" width="6" height="6" fill="var(--borg-cyan)" opacity="0.5"/>
				<rect x="8" y="18" width="6" height="6" fill="var(--borg-cyan)" opacity="0.5"/>
				<rect x="18" y="18" width="6" height="6" fill="var(--borg-cyan)" opacity="0.8"/>
			</svg>
			<h1>BorgOS</h1>
			<p class="login-subtitle">RESISTANCE IS FUTILE</p>
		</div>

		<form class="login-form" onsubmit={handleSubmit} novalidate>
			<div class="form-field">
				<label for="username" class="form-label">Identity</label>
				<BorgInput
					id="username"
					name="username"
					type="text"
					bind:value={username}
					placeholder="borg"
					autocomplete="username"
					autofocus
					disabled={loading}
				/>
			</div>

			<div class="form-field">
				<label for="password" class="form-label">Access Code</label>
				<BorgInput
					id="password"
					name="password"
					type="password"
					bind:value={password}
					placeholder="••••••••"
					autocomplete="current-password"
					disabled={loading}
				/>
			</div>

			{#if errorMsg}
				<div class="login-error" role="alert" aria-live="polite">
					⚠ {errorMsg}
				</div>
			{/if}

			<BorgButton type="submit" variant="primary" disabled={loading} class="login-submit">
				{loading ? 'ASSIMILATING...' : 'ASSIMILATE'}
			</BorgButton>
		</form>
	</div>
</div>

<style>
	.login-page {
		min-height: 100vh;
		background-color: var(--borg-black);
		background-image: url('/borg-hex-pattern.svg');
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
	}

	.login-container {
		width: 100%;
		max-width: 400px;
		background-color: var(--borg-void);
		border: 1px solid var(--borg-border);
		padding: 48px;
		box-shadow: 0 0 40px rgba(0, 229, 255, 0.05);
		position: relative;
		z-index: 1;
	}

	.login-header {
		text-align: center;
		margin-bottom: 40px;
	}

	.login-header h1 {
		font-family: 'Share Tech Mono', monospace;
		font-size: 32px;
		color: var(--borg-cyan);
		margin: 12px 0 8px;
		letter-spacing: 0.2em;
		text-shadow: var(--glow-cyan);
	}

	.login-subtitle {
		font-size: 11px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.3em;
		text-transform: uppercase;
		margin: 0;
	}

	.login-form {
		display: flex;
		flex-direction: column;
		gap: 20px;
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

	.login-error {
		color: var(--borg-red);
		font-size: 13px;
		padding: 8px 12px;
		border: 1px solid var(--borg-red);
		background-color: rgba(255, 34, 68, 0.08);
	}

	:global(.login-submit) {
		width: 100%;
		justify-content: center;
		padding: 12px;
	}
</style>
