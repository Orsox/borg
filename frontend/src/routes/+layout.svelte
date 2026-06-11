<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { authStore, isAuthenticated } from '$lib/stores/auth';
	import { getMe } from '$lib/api/client';
	import BorgNav from '$lib/components/BorgNav.svelte';
	import BorgStatusBar from '$lib/components/BorgStatusBar.svelte';
	import BorgToast from '$lib/components/BorgToast.svelte';
	import HexLoader from '$lib/components/HexLoader.svelte';
	import CommandPalette from '$lib/components/CommandPalette.svelte';

	let { children } = $props();

	const publicRoutes = ['/login'];

	onMount(async () => {
		const token = authStore.getToken();
		if (token) {
			authStore.setToken(token);
			try {
				const user = await getMe();
				authStore.setUser(user);
			} catch {
				authStore.logout();
			}
		} else {
			authStore.setLoading(false);
		}
	});

	$effect(() => {
		const path = $page.url.pathname;
		const loading = $authStore.loading;
		const authed = $isAuthenticated;

		if (!loading) {
			if (!authed && !publicRoutes.includes(path)) {
				goto('/login');
			} else if (authed && path === '/login') {
				goto('/');
			}
		}
	});

	const isPublic = $derived(publicRoutes.includes($page.url.pathname));
</script>

{#if isPublic}
	{@render children()}
{:else if $authStore.loading}
	<div class="loading-overlay" aria-label="Loading application">
		<HexLoader size={64} />
		<p>INITIALIZING BORGOS...</p>
	</div>
{:else if $isAuthenticated}
	<div class="app-shell">
		<BorgNav />
		<div class="app-main">
			<BorgStatusBar />
			<main class="app-content">
				{@render children()}
			</main>
		</div>
	</div>
	<CommandPalette />
{/if}

<BorgToast />

<style>
	.loading-overlay {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		min-height: 100vh;
		background-color: var(--borg-black);
		background-image: url('/borg-hex-pattern.svg');
		gap: 24px;
		color: var(--borg-cyan);
		font-family: 'Share Tech Mono', monospace;
		font-size: 14px;
		letter-spacing: 0.2em;
	}

	.app-shell {
		display: flex;
		min-height: 100vh;
		background-color: var(--borg-black);
		background-image: url('/borg-hex-pattern.svg');
	}

	.app-main {
		flex: 1;
		margin-left: 220px;
		display: flex;
		flex-direction: column;
		min-height: 100vh;
	}

	.app-content {
		flex: 1;
		padding: 24px;
		overflow-y: auto;
	}
</style>
