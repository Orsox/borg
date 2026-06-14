<script lang="ts">
	import { page } from '$app/stores';
	import { authStore } from '$lib/stores/auth';
	import { goto } from '$app/navigation';

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: '⬡' },
		{ href: '/archon', label: 'Archon Hub', icon: '◈' },
		{ href: '/brain', label: 'Second Brain', icon: '◉' },
		{ href: '/tasks', label: 'Task Automation', icon: '◆' },
		{ href: '/meeting', label: 'Conference', icon: '◇' },
		{ href: '/observability', label: 'Observability', icon: '◎' },
		{ href: '/sync', label: 'Peer Sync', icon: '⇄' },
		{ href: '/personas', label: 'Personas', icon: '◎' },
		{ href: '/settings', label: 'Settings', icon: '⚙' },
	];

	function isAdminNavItem() {
		return $authStore.user?.is_admin
			? { href: '/users', label: 'Users', icon: '◈' }
			: null;
	}

	function isActive(href: string) {
		if (href === '/') return $page.url.pathname === '/';
		return $page.url.pathname.startsWith(href);
	}

	async function logout() {
		authStore.logout();
		await goto('/login');
	}
</script>

<nav class="borg-nav" aria-label="Main navigation">
	<div class="nav-logo">
		<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
			<rect x="4" y="4" width="24" height="24" fill="none" stroke="var(--borg-cyan)" stroke-width="1.5"/>
			<rect x="8" y="8" width="6" height="6" fill="var(--borg-cyan)" opacity="0.8"/>
			<rect x="18" y="8" width="6" height="6" fill="var(--borg-cyan)" opacity="0.5"/>
			<rect x="8" y="18" width="6" height="6" fill="var(--borg-cyan)" opacity="0.5"/>
			<rect x="18" y="18" width="6" height="6" fill="var(--borg-cyan)" opacity="0.8"/>
		</svg>
		<span class="nav-logo-text">BorgOS</span>
	</div>

	<div class="nav-divider"></div>

	<ul class="nav-items" role="list">
		{#each navItems as item}
			<li>
				<a
					href={item.href}
					class="nav-item"
					class:nav-item--active={isActive(item.href)}
					aria-current={isActive(item.href) ? 'page' : undefined}
				>
					<span class="nav-item-icon" aria-hidden="true">{item.icon}</span>
					<span class="nav-item-label">{item.label}</span>
				</a>
			</li>
		{/each}
		{#if isAdminNavItem()}
			<li>
				<a
					href="/users"
					class="nav-item"
					class:nav-item--active={$page.url.pathname.startsWith('/users')}
					aria-current={$page.url.pathname.startsWith('/users') ? 'page' : undefined}
				>
					<span class="nav-item-icon" aria-hidden="true">{isAdminNavItem()!.icon}</span>
					<span class="nav-item-label">{isAdminNavItem()!.label}</span>
				</a>
			</li>
		{/if}
	</ul>

	<div class="nav-divider"></div>
	<div class="nav-bottom">
		<span class="nav-user" aria-label="Current user">
			{$authStore.user?.username ?? ''}
		</span>
		<button class="nav-logout" onclick={logout} aria-label="Log out">
			Logout
		</button>
	</div>
</nav>

<style>
	.borg-nav {
		width: 220px;
		min-width: 220px;
		background-color: var(--borg-void);
		border-right: 1px solid var(--borg-border);
		display: flex;
		flex-direction: column;
		height: 100vh;
		position: fixed;
		left: 0;
		top: 0;
		z-index: 100;
		overflow-y: auto;
	}

	.nav-logo {
		padding: 24px 16px;
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.nav-logo-text {
		font-family: 'Share Tech Mono', monospace;
		font-size: 18px;
		color: var(--borg-cyan);
		letter-spacing: 0.1em;
	}

	.nav-divider {
		height: 1px;
		background-color: var(--borg-border);
		margin: 0 16px;
	}

	.nav-items {
		list-style: none;
		margin: 0;
		padding: 8px 0;
		flex: 1;
	}

	.nav-item {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 16px;
		color: var(--borg-text-secondary);
		text-decoration: none;
		font-size: 13px;
		transition: all 150ms ease-out;
		border-left: 3px solid transparent;
	}

	.nav-item:hover {
		color: var(--borg-text-primary);
		background-color: rgba(0, 229, 255, 0.04);
		border-left-color: var(--borg-border-active);
	}

	.nav-item--active {
		color: var(--borg-cyan);
		border-left-color: var(--borg-cyan);
		background-color: rgba(0, 229, 255, 0.06);
	}

	.nav-item-icon {
		font-size: 16px;
		width: 20px;
		text-align: center;
	}

	.nav-bottom {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.nav-user {
		font-size: 11px;
		color: var(--borg-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.nav-logout {
		background: none;
		border: 1px solid var(--borg-border);
		color: var(--borg-text-secondary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		padding: 6px 12px;
		cursor: pointer;
		text-align: left;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		transition: all 150ms ease-out;
	}

	.nav-logout:hover {
		border-color: var(--borg-red);
		color: var(--borg-red);
	}
</style>
