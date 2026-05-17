<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { getHealth } from '$lib/api/client';

	let utcTime = $state('--:--:-- UTC');
	let dbStatus = $state<'online' | 'error'>('online');
	let schedulerStatus = $state<'online' | 'error'>('online');
	let interval: ReturnType<typeof setInterval>;

	function updateClock() {
		const now = new Date();
		const h = now.getUTCHours().toString().padStart(2, '0');
		const m = now.getUTCMinutes().toString().padStart(2, '0');
		const s = now.getUTCSeconds().toString().padStart(2, '0');
		utcTime = `${h}:${m}:${s} UTC`;
	}

	async function checkHealth() {
		try {
			const health = await getHealth();
			dbStatus = health.status === 'nominal' ? 'online' : 'error';
			schedulerStatus = health.modules?.task_automation === 'online' ? 'online' : 'error';
		} catch {
			dbStatus = 'error';
			schedulerStatus = 'error';
		}
	}

	onMount(() => {
		updateClock();
		interval = setInterval(updateClock, 1000);
		checkHealth();
	});

	onDestroy(() => {
		clearInterval(interval);
	});

	const statusColor = (s: string) => s === 'online' ? 'var(--borg-green)' : 'var(--borg-red)';
</script>

<div class="status-bar" role="status" aria-label="System status">
	<span class="status-clock flicker" aria-label="UTC time">{utcTime}</span>
	<div class="status-divider"></div>
	<span class="status-indicator" aria-label="Database status">
		<span class="status-dot" style="background-color: {statusColor(dbStatus)};" aria-hidden="true"></span>
		DB
	</span>
	<div class="status-divider"></div>
	<span class="status-indicator" aria-label="Scheduler status">
		<span class="status-dot" style="background-color: {statusColor(schedulerStatus)};" aria-hidden="true"></span>
		SCHED
	</span>
</div>

<style>
	.status-bar {
		height: 32px;
		background-color: var(--borg-panel);
		border-bottom: 1px solid var(--borg-border);
		display: flex;
		align-items: center;
		padding: 0 16px;
		gap: 0;
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	.status-clock {
		color: var(--borg-cyan);
		letter-spacing: 0.05em;
		min-width: 120px;
	}

	.status-divider {
		width: 1px;
		height: 16px;
		background-color: var(--borg-border);
		margin: 0 12px;
	}

	.status-indicator {
		display: flex;
		align-items: center;
		gap: 6px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.status-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
	}
</style>
