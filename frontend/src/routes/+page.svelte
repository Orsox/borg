<script lang="ts">
	import { currentUser } from '$lib/stores/auth';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import ArchonSystemPanel from '$lib/components/ArchonSystemPanel.svelte';
</script>

<svelte:head>
	<title>BorgOS — Dashboard</title>
</svelte:head>

<div class="dashboard">
	<header class="dashboard-header">
		<h1>BORGOS DASHBOARD</h1>
		<p class="subtitle">Welcome, {$currentUser?.username ?? ''}. You have been assimilated.</p>
	</header>

	<ArchonSystemPanel />

	<div class="module-grid">
		<BorgPanel class="module-card">
			<div class="module-card-inner">
				<div class="module-icon">◈</div>
				<h2>Archon Hub</h2>
				<p>Manage AI assets, workflows, and agents</p>
				<a href="/archon" class="module-link">Access Module →</a>
			</div>
		</BorgPanel>

		<BorgPanel class="module-card">
			<div class="module-card-inner">
				<div class="module-icon">◉</div>
				<h2>Second Brain</h2>
				<p>Knowledge graph, notes, and wiki-links</p>
				<a href="/brain" class="module-link">Access Module →</a>
			</div>
		</BorgPanel>

		<BorgPanel class="module-card">
			<div class="module-card-inner">
				<div class="module-icon">◆</div>
				<h2>Task Automation</h2>
				<p>Scheduled tasks, cron jobs, execution history</p>
				<a href="/tasks" class="module-link">Access Module →</a>
			</div>
		</BorgPanel>
	</div>
</div>

<style>
	.dashboard {
		max-width: 1200px;
	}

	.dashboard-header {
		margin-bottom: 32px;
		padding-bottom: 24px;
		border-bottom: 1px solid var(--borg-border);
		position: relative;
		overflow: hidden;
	}

	.dashboard-header::after {
		content: '';
		position: absolute;
		bottom: -1px;
		left: 0;
		width: 60px;
		height: 2px;
		background-color: var(--borg-cyan);
	}

	.dashboard-header h1 {
		font-size: 28px;
		color: var(--borg-cyan);
		margin: 0 0 8px;
		letter-spacing: 0.15em;
	}

	.subtitle {
		color: var(--borg-text-secondary);
		font-size: 13px;
		margin: 0;
	}

	.module-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 16px;
	}

	:global(.module-card) {
		transition: border-color 150ms ease-out;
	}

	:global(.module-card:hover) {
		border-color: var(--borg-border-active);
	}

	.module-card-inner {
		padding: 32px;
	}

	.module-icon {
		font-size: 32px;
		color: var(--borg-cyan);
		margin-bottom: 16px;
	}

	.module-card-inner h2 {
		font-family: 'Share Tech Mono', monospace;
		font-size: 18px;
		margin: 0 0 8px;
		color: var(--borg-text-primary);
		letter-spacing: 0.1em;
	}

	.module-card-inner p {
		color: var(--borg-text-secondary);
		font-size: 13px;
		margin: 0 0 24px;
	}

	.module-link {
		color: var(--borg-cyan);
		font-size: 12px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		text-decoration: none;
	}

	.module-link:hover {
		text-decoration: underline;
	}
</style>
