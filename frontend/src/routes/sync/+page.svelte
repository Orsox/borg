<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import HexLoader from '$lib/components/HexLoader.svelte';
	import {
		listPeers, createPeer, deletePeer, startSync, runComparison,
		setDecision, applyItem
	} from '$lib/api/peerSync';
	import type { Peer, SyncRun, SyncItem, DiffStatus } from '$lib/api/peerSync';

	let peers = $state<Peer[]>([]);
	let run = $state<SyncRun | null>(null);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let expanded = $state<number | null>(null);

	// New-peer form
	let newLabel = $state('');
	let newUrl = $state('');
	let newToken = $state('');

	const STATUS_ORDER: DiffStatus[] = ['changed', 'only_remote', 'only_local'];
	const STATUS_LABEL: Record<DiffStatus, string> = {
		changed: 'CHANGED',
		only_remote: 'ONLY REMOTE',
		only_local: 'ONLY LOCAL'
	};

	function statusBadge(s: DiffStatus): 'idle' | 'assimilated' | 'default' {
		if (s === 'changed') return 'idle';
		if (s === 'only_remote') return 'assimilated';
		return 'default';
	}

	const grouped = $derived.by(() => {
		const out: Record<DiffStatus, SyncItem[]> = { changed: [], only_remote: [], only_local: [] };
		for (const it of run?.items ?? []) out[it.status]?.push(it);
		return out;
	});

	async function refreshPeers() {
		try {
			peers = await listPeers();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	onMount(refreshPeers);

	async function addPeer() {
		if (!newLabel.trim() || !newUrl.trim()) return;
		busy = true;
		error = '';
		try {
			await createPeer(newLabel.trim(), newUrl.trim(), newToken.trim());
			newLabel = newUrl = newToken = '';
			await refreshPeers();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	async function removePeer(id: number) {
		busy = true;
		try {
			await deletePeer(id);
			if (run?.peer_id === id) run = null;
			await refreshPeers();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	async function sync(peer: Peer) {
		busy = true;
		error = '';
		run = null;
		try {
			run = await startSync(peer.id);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	async function compare() {
		if (!run) return;
		busy = true;
		error = '';
		try {
			run = await runComparison(run.id);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	async function decide(item: SyncItem, decision: 'accept' | 'reject') {
		busy = true;
		try {
			await setDecision(item.id, decision);
			item.decision = decision === 'accept' ? 'accepted' : 'rejected';
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	async function accept(item: SyncItem) {
		busy = true;
		error = '';
		try {
			await setDecision(item.id, 'accept');
			await applyItem(item.id);
			item.decision = 'applied';
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	function toggle(id: number) {
		expanded = expanded === id ? null : id;
	}
</script>

<div class="sync-page">
	<header class="page-head">
		<h1>Peer Sync</h1>
		<p class="subtitle">
			Connect to another local BorgOS and synchronize Archon workflows, skills and agents.
			Differences are found by static diff, then analysed by Seven of Nine before you apply them.
		</p>
	</header>

	{#if error}
		<div class="error-bar">{error}</div>
	{/if}

	<BorgPanel>
		{#snippet header()}Registered Peers{/snippet}
		<div class="panel-body">
			{#if loading}
				<HexLoader />
			{:else}
				{#if peers.length === 0}
					<p class="muted">No peers registered yet. Add one below.</p>
				{/if}
				<ul class="peer-list">
					{#each peers as peer}
						<li class="peer-row">
							<div class="peer-meta">
								<span class="peer-label">{peer.label}</span>
								<span class="peer-url">{peer.base_url}</span>
							</div>
							<div class="peer-actions">
								<BorgButton variant="secondary" disabled={busy} onclick={() => sync(peer)}>Sync</BorgButton>
								<BorgButton variant="danger" disabled={busy} onclick={() => removePeer(peer.id)}>Remove</BorgButton>
							</div>
						</li>
					{/each}
				</ul>

				<div class="add-peer">
					<BorgInput placeholder="Label (e.g. Workstation)" bind:value={newLabel} />
					<BorgInput placeholder="Base URL (e.g. http://192.168.1.50:1742)" bind:value={newUrl} />
					<BorgInput placeholder="Peer token" type="password" bind:value={newToken} />
					<BorgButton disabled={busy} onclick={addPeer}>Add Peer</BorgButton>
				</div>
			{/if}
		</div>
	</BorgPanel>

	{#if busy && !run}
		<div class="loader-center"><HexLoader /></div>
	{/if}

	{#if run}
		<BorgPanel class="run-panel">
			{#snippet header()}Diff — run #{run?.id}{/snippet}
			<div class="panel-body">
				<div class="run-summary">
					{#each Object.entries(run?.counts ?? {}) as [k, v]}
						<span class="count-chip">{k}: {v}</span>
					{/each}
					<div class="spacer"></div>
					<BorgButton
						disabled={busy || run.status === 'compared'}
						onclick={compare}
					>
						{run.status === 'compared' ? 'Compared by Seven' : 'Compare with Seven'}
					</BorgButton>
				</div>

				{#if run.items.length === 0}
					<p class="muted">No differences — both instances are in sync.</p>
				{/if}

				{#each STATUS_ORDER as status}
					{#if grouped[status].length > 0}
						<h3 class="group-head">{STATUS_LABEL[status]} ({grouped[status].length})</h3>
						<ul class="item-list">
							{#each grouped[status] as item}
								<li class="item-row">
									<button class="item-summary" onclick={() => toggle(item.id)}>
										<BorgBadge status={statusBadge(item.status)}>{item.kind}</BorgBadge>
										<span class="item-name">{item.name}</span>
										<span class="item-identity">{item.identity}</span>
										<span class="item-decision">
											{#if item.decision !== 'pending'}
												<BorgBadge status={item.decision === 'applied' || item.decision === 'accepted' ? 'online' : 'error'}>
													{item.decision}
												</BorgBadge>
											{/if}
										</span>
									</button>

									{#if expanded === item.id}
										<div class="item-detail">
											{#if item.analysis}
												<div class="analysis">
													{#if item.analysis.error}
														<p class="analysis-error">{item.analysis.error}</p>
													{:else if item.analysis.rationale}
														<p>{item.analysis.rationale}</p>
													{:else}
														{#if item.analysis.semantic_summary}
															<p><strong>Difference:</strong> {item.analysis.semantic_summary}</p>
														{/if}
														{#if item.analysis.recommendation}
															<p><strong>Recommendation:</strong>
																<BorgBadge status="assimilated">{item.analysis.recommendation.winner}</BorgBadge>
																{item.analysis.recommendation.merge_notes}
															</p>
														{/if}
														{#if item.analysis.risk}
															<p><strong>Risk:</strong> {item.analysis.risk}</p>
														{/if}
													{/if}
												</div>
											{:else}
												<p class="muted">Not yet analysed by Seven.</p>
											{/if}

											<div class="content-grid">
												<div>
													<div class="content-label">Local</div>
													<pre class="content-box">{item.local_content ?? '(none)'}</pre>
												</div>
												<div>
													<div class="content-label">Remote</div>
													<pre class="content-box">{item.remote_content ?? '(none)'}</pre>
												</div>
											</div>

											{#if item.status !== 'only_local' && item.decision !== 'applied'}
												<div class="item-actions">
													<BorgButton disabled={busy} onclick={() => accept(item)}>Accept &amp; Apply</BorgButton>
													<BorgButton variant="ghost" disabled={busy} onclick={() => decide(item, 'reject')}>Reject</BorgButton>
												</div>
											{/if}
										</div>
									{/if}
								</li>
							{/each}
						</ul>
					{/if}
				{/each}
			</div>
		</BorgPanel>
	{/if}
</div>

<style>
	.sync-page {
		padding: 24px;
		max-width: 1100px;
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.page-head h1 {
		font-family: 'Share Tech Mono', monospace;
		color: var(--borg-cyan);
		letter-spacing: 0.08em;
		margin: 0 0 6px;
	}

	.subtitle {
		color: var(--borg-text-secondary);
		font-size: 13px;
		max-width: 70ch;
		margin: 0;
	}

	.error-bar {
		border: 1px solid var(--borg-red);
		color: var(--borg-red);
		padding: 10px 14px;
		font-size: 13px;
	}

	.panel-body { padding: 16px; }
	.muted { color: var(--borg-text-secondary); font-size: 13px; }

	.peer-list { list-style: none; margin: 0 0 16px; padding: 0; }
	.peer-row {
		display: flex; align-items: center; justify-content: space-between;
		padding: 10px 0; border-bottom: 1px solid var(--borg-border);
	}
	.peer-meta { display: flex; flex-direction: column; gap: 2px; }
	.peer-label { color: var(--borg-text-primary); font-size: 14px; }
	.peer-url { color: var(--borg-text-secondary); font-size: 12px; }
	.peer-actions { display: flex; gap: 8px; }

	.add-peer {
		display: grid;
		grid-template-columns: 1fr 1.6fr 1fr auto;
		gap: 8px;
		align-items: center;
		padding-top: 12px;
		border-top: 1px solid var(--borg-border);
	}

	.loader-center { display: flex; justify-content: center; padding: 24px; }

	.run-summary { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
	.count-chip {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		color: var(--borg-text-secondary);
		border: 1px solid var(--borg-border);
		padding: 2px 8px;
	}
	.spacer { flex: 1; }

	.group-head {
		font-family: 'Share Tech Mono', monospace;
		font-size: 12px;
		letter-spacing: 0.08em;
		color: var(--borg-text-secondary);
		margin: 18px 0 8px;
	}

	.item-list { list-style: none; margin: 0; padding: 0; }
	.item-row { border: 1px solid var(--borg-border); margin-bottom: 6px; }
	.item-summary {
		display: flex; align-items: center; gap: 12px;
		width: 100%; background: none; border: none; cursor: pointer;
		padding: 10px 12px; text-align: left;
		color: var(--borg-text-primary); font-size: 13px;
	}
	.item-summary:hover { background-color: rgba(0, 229, 255, 0.04); }
	.item-name { font-weight: 600; }
	.item-identity { color: var(--borg-text-secondary); font-size: 12px; }
	.item-decision { margin-left: auto; }

	.item-detail { padding: 12px; border-top: 1px solid var(--borg-border); }
	.analysis { font-size: 13px; color: var(--borg-text-primary); margin-bottom: 12px; }
	.analysis p { margin: 4px 0; }
	.analysis-error { color: var(--borg-red); }

	.content-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
	.content-label {
		font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
		color: var(--borg-text-secondary); margin-bottom: 4px;
	}
	.content-box {
		background-color: var(--borg-void);
		border: 1px solid var(--borg-border);
		padding: 8px; font-size: 12px; max-height: 260px; overflow: auto;
		white-space: pre-wrap; word-break: break-word; margin: 0;
		font-family: 'JetBrains Mono', monospace;
	}

	.item-actions { display: flex; gap: 8px; }
</style>
