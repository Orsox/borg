<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import HexLoader from '$lib/components/HexLoader.svelte';
	import {
		getPersonas, startMeeting, getSession, sendMessage, parseMeetingInput
	} from '$lib/api/meeting';
	import type { Persona, MeetingSession } from '$lib/api/meeting';

	let personas = $state<Persona[]>([]);
	let session = $state<MeetingSession | null>(null);
	let inputText = $state('');
	let error = $state('');
	let busy = $state(false);

	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let transcriptEl = $state<HTMLDivElement | null>(null);

	const running = $derived(session?.status === 'running');

	const statusLine = $derived.by(() => {
		if (error) return `⚠ ${error}`;
		if (!session) return 'Kein aktives Meeting. Gib ein Thema ein, um die Sitzung zu eröffnen.';
		if (session.status === 'error') return `Sitzung abgebrochen — ${session.error ?? 'Fehler'}`;
		if (session.status === 'done') return `Sitzung beendet — ${session.rounds_done} Runde(n).`;
		if (session.speaking) {
			const p = personas.find((x) => x.key === session!.speaking);
			return `${p?.display_name ?? session.speaking} spricht…`;
		}
		return 'Runde läuft…';
	});

	function colorFor(key: string): string {
		return personas.find((p) => p.key === key)?.color ?? 'var(--borg-cyan)';
	}

	function initialFor(name: string): string {
		const m = name.match(/\d+/);
		return m ? m[0] : name.charAt(0).toUpperCase();
	}

	function stopPolling() {
		if (pollTimer) {
			clearInterval(pollTimer);
			pollTimer = null;
		}
	}

	function ensurePolling() {
		if (pollTimer) return;
		pollTimer = setInterval(async () => {
			if (!session) return;
			try {
				session = await getSession(session.id);
				if (session.status !== 'running') stopPolling();
			} catch (e) {
				error = e instanceof Error ? e.message : String(e);
				stopPolling();
			}
		}, 1200);
	}

	async function submit() {
		const parsed = parseMeetingInput(inputText);
		if (!parsed || busy || running) return;
		error = '';
		busy = true;
		const startsNew = !session || /^\/meeting\b/i.test(inputText.trim());
		try {
			if (startsNew) {
				session = await startMeeting(parsed.text, parsed.rounds);
			} else {
				session = await sendMessage(session!.id, parsed.text, parsed.rounds);
			}
			inputText = '';
			ensurePolling();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}

	function onSubmit(e: SubmitEvent) {
		e.preventDefault();
		submit();
	}

	// Auto-scroll the transcript as new turns arrive.
	$effect(() => {
		if (session?.transcript.length && transcriptEl) {
			transcriptEl.scrollTop = transcriptEl.scrollHeight;
		}
	});

	onMount(async () => {
		try {
			personas = await getPersonas();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	});

	onDestroy(stopPolling);
</script>

<div class="meeting">
	<header class="meeting-head">
		<h1>Konferenzraum</h1>
		<div class="status-line" class:status-error={!!error || session?.status === 'error'}>
			{statusLine}
		</div>
	</header>

	<!-- The Borg conference table: persona stations around the arc, Orsox at the seat. -->
	<div class="stage">
		<div class="table">
			<div class="table-core">
				{#if running && !session?.speaking}
					<HexLoader size={28} />
				{/if}
				<span class="table-label">UNIMATRIX · KONFERENZ</span>
			</div>
		</div>

		<div class="stations">
			{#each personas as p (p.key)}
				<div
					class="station"
					class:station--active={session?.speaking === p.key}
					class:station--dim={running && session?.speaking && session.speaking !== p.key}
					style="--accent: {p.color}"
				>
					<div class="avatar">
						<span class="avatar-initial">{initialFor(p.display_name)}</span>
						<div class="ring"></div>
						{#if session?.speaking === p.key}
							<div class="eq" aria-hidden="true">
								<span></span><span></span><span></span><span></span><span></span>
							</div>
						{/if}
					</div>
					<div class="station-name">{p.display_name}</div>
				</div>
			{/each}
		</div>

		<div class="seat">
			<div class="seat-hex">DU</div>
			<div class="seat-name">Orsox</div>
		</div>
	</div>

	<!-- Transcript -->
	<BorgPanel class="transcript-panel">
		{#snippet header()}Protokoll{/snippet}
		<div class="transcript" bind:this={transcriptEl}>
			{#if !session}
				<p class="empty">Noch keine Sitzung. Eröffne eine mit einem Thema unten.</p>
			{:else}
				{#each session.transcript as turn, i (i)}
					<div class="turn">
						<span class="turn-speaker" style="color: {turn.speaker === 'orsox' ? 'var(--borg-amber)' : colorFor(turn.speaker)}">
							{turn.display_name}
						</span>
						<span class="turn-content">{turn.content}</span>
					</div>
				{/each}
				{#if running}
					<div class="turn turn--pending">
						<HexLoader size={18} />
						<span class="turn-content">{statusLine}</span>
					</div>
				{/if}
			{/if}
		</div>
	</BorgPanel>

	<!-- Input bar -->
	<form class="input-bar" onsubmit={onSubmit}>
		<BorgInput
			bind:value={inputText}
			placeholder={session ? 'Nachricht an den Tisch…' : '/meeting 3 <Thema> — oder einfach ein Thema'}
			disabled={busy || running}
			class="input-grow"
		/>
		<BorgButton type="submit" disabled={busy || running || !inputText.trim()}>
			{session ? 'Senden' : 'Eröffnen'}
		</BorgButton>
	</form>
	<p class="hint">
		Codewort <code>/meeting &lt;Runden&gt; &lt;Thema&gt;</code> startet eine neue Sitzung
		(jede Runde = jeder Charakter spricht einmal). Ohne Zahl: 3 Runden.
	</p>
</div>

<style>
	.meeting {
		display: flex;
		flex-direction: column;
		gap: 16px;
		max-width: 1100px;
		margin: 0 auto;
		padding: 8px 4px 24px;
	}

	.meeting-head h1 {
		font-family: 'Share Tech Mono', monospace;
		font-size: 22px;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--borg-cyan);
		margin: 0;
	}

	.status-line {
		font-family: 'Share Tech Mono', monospace;
		font-size: 13px;
		color: var(--borg-text-secondary);
		margin-top: 4px;
	}
	.status-error {
		color: var(--borg-red);
	}

	/* --- Stage / table --- */
	.stage {
		position: relative;
		background:
			radial-gradient(ellipse at 50% 35%, rgba(0, 229, 255, 0.06), transparent 60%),
			var(--borg-void);
		border: 1px solid var(--borg-border);
		padding: 24px 16px 16px;
		min-height: 260px;
		overflow: hidden;
	}

	.table {
		position: relative;
		margin: 70px auto 0;
		width: min(560px, 88%);
		height: 150px;
		border: 1px solid var(--borg-border-active);
		border-radius: 50% / 60%;
		background:
			radial-gradient(ellipse at center, rgba(0, 229, 255, 0.05), transparent 70%);
		box-shadow: inset 0 0 40px rgba(0, 229, 255, 0.08);
	}
	.table-core {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 6px;
	}
	.table-label {
		font-family: 'Share Tech Mono', monospace;
		font-size: 11px;
		letter-spacing: 0.22em;
		color: var(--borg-text-disabled);
	}

	.stations {
		position: absolute;
		top: 18px;
		left: 0;
		right: 0;
		display: flex;
		justify-content: center;
		gap: clamp(32px, 12vw, 140px);
	}

	.station {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		transition: opacity 0.4s ease, transform 0.4s ease;
	}
	.station--dim {
		opacity: 0.4;
	}
	.station--active {
		transform: translateY(-4px);
	}

	.avatar {
		position: relative;
		width: 76px;
		height: 86px;
		display: flex;
		align-items: center;
		justify-content: center;
		/* hexagon */
		clip-path: polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%);
		background: linear-gradient(160deg, rgba(255, 255, 255, 0.04), transparent);
		border: 1px solid color-mix(in srgb, var(--accent) 50%, transparent);
		color: var(--accent);
		animation: idle-pulse 3s ease-in-out infinite;
	}
	.station--active .avatar {
		animation: active-pulse 1.1s ease-in-out infinite;
		box-shadow: 0 0 18px color-mix(in srgb, var(--accent) 60%, transparent);
	}
	.avatar-initial {
		font-family: 'Share Tech Mono', monospace;
		font-size: 30px;
		font-weight: 700;
		text-shadow: 0 0 8px color-mix(in srgb, var(--accent) 70%, transparent);
	}

	.ring {
		position: absolute;
		inset: -7px;
		clip-path: polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%);
		border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
		opacity: 0;
	}
	.station--active .ring {
		animation: ring-expand 1.1s ease-out infinite;
	}

	.eq {
		position: absolute;
		bottom: -14px;
		display: flex;
		align-items: flex-end;
		gap: 3px;
		height: 14px;
	}
	.eq span {
		width: 3px;
		height: 4px;
		background: var(--accent);
		animation: eq-bounce 0.7s ease-in-out infinite;
	}
	.eq span:nth-child(2) { animation-delay: 0.1s; }
	.eq span:nth-child(3) { animation-delay: 0.2s; }
	.eq span:nth-child(4) { animation-delay: 0.3s; }
	.eq span:nth-child(5) { animation-delay: 0.15s; }

	.station-name {
		font-family: 'Share Tech Mono', monospace;
		font-size: 12px;
		letter-spacing: 0.08em;
		color: var(--borg-text-primary);
	}

	.seat {
		position: absolute;
		bottom: 14px;
		left: 50%;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}
	.seat-hex {
		width: 52px;
		height: 58px;
		display: flex;
		align-items: center;
		justify-content: center;
		clip-path: polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%);
		border: 1px solid var(--borg-amber);
		color: var(--borg-amber);
		font-family: 'Share Tech Mono', monospace;
		font-size: 13px;
	}
	.seat-name {
		font-family: 'Share Tech Mono', monospace;
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	@keyframes idle-pulse {
		0%, 100% { opacity: 0.75; }
		50% { opacity: 1; }
	}
	@keyframes active-pulse {
		0%, 100% { filter: brightness(1); }
		50% { filter: brightness(1.5); }
	}
	@keyframes ring-expand {
		0% { opacity: 0.7; inset: -3px; }
		100% { opacity: 0; inset: -16px; }
	}
	@keyframes eq-bounce {
		0%, 100% { height: 4px; }
		50% { height: 14px; }
	}

	/* --- Transcript --- */
	:global(.transcript-panel) {
		display: flex;
		flex-direction: column;
	}
	.transcript {
		max-height: 320px;
		overflow-y: auto;
		padding: 12px 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.empty {
		color: var(--borg-text-disabled);
		font-family: 'Share Tech Mono', monospace;
		font-size: 13px;
	}
	.turn {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.turn--pending {
		flex-direction: row;
		align-items: center;
		gap: 10px;
		opacity: 0.7;
	}
	.turn-speaker {
		font-family: 'Share Tech Mono', monospace;
		font-size: 12px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}
	.turn-content {
		color: var(--borg-text-primary);
		font-size: 14px;
		line-height: 1.5;
		white-space: pre-wrap;
	}

	/* --- Input --- */
	.input-bar {
		display: flex;
		gap: 10px;
		align-items: stretch;
	}
	:global(.input-grow) {
		flex: 1;
	}
	.hint {
		font-family: 'Share Tech Mono', monospace;
		font-size: 11px;
		color: var(--borg-text-disabled);
		margin: 0;
	}
	.hint code {
		color: var(--borg-text-secondary);
	}
</style>
