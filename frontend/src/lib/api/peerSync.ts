import { apiFetch } from './client';

// --- Types ---
export interface Peer {
	id: number;
	label: string;
	base_url: string;
	is_active: boolean;
	last_synced_at: string | null;
	created_at: string;
}

export interface MergeRecommendation {
	winner: string;
	merge_notes: string;
}

export interface SyncAnalysis {
	semantic_summary?: string;
	recommendation?: MergeRecommendation;
	risk?: string;
	rationale?: string;
	error?: string;
}

export type SyncKind = 'workflow' | 'skill' | 'agent' | 'skill_db';
export type DiffStatus = 'only_remote' | 'only_local' | 'changed';
export type Decision = 'pending' | 'accepted' | 'rejected' | 'applied';

export interface SyncItem {
	id: number;
	kind: SyncKind;
	identity: string;
	name: string;
	status: DiffStatus;
	local_hash: string | null;
	remote_hash: string | null;
	local_content: string | null;
	remote_content: string | null;
	analysis: SyncAnalysis | null;
	decision: Decision;
}

export interface SyncRun {
	id: number;
	peer_id: number;
	status: string;
	counts: Record<string, number>;
	started_at: string;
	finished_at: string | null;
	items: SyncItem[];
}

// --- API functions ---
export async function listPeers(): Promise<Peer[]> {
	return apiFetch<Peer[]>('/peer-sync/peers');
}

export async function createPeer(label: string, baseUrl: string, token: string): Promise<Peer> {
	return apiFetch<Peer>('/peer-sync/peers', {
		method: 'POST',
		body: JSON.stringify({ label, base_url: baseUrl, token })
	});
}

export async function deletePeer(peerId: number): Promise<void> {
	await apiFetch(`/peer-sync/peers/${peerId}`, { method: 'DELETE' });
}

export async function startSync(peerId: number): Promise<SyncRun> {
	return apiFetch<SyncRun>(`/peer-sync/peers/${peerId}/sync`, { method: 'POST' });
}

export async function runComparison(runId: number): Promise<SyncRun> {
	return apiFetch<SyncRun>(`/peer-sync/runs/${runId}/compare`, { method: 'POST' });
}

export async function getRun(runId: number): Promise<SyncRun> {
	return apiFetch<SyncRun>(`/peer-sync/runs/${runId}`);
}

export async function setDecision(itemId: number, decision: 'accept' | 'reject') {
	return apiFetch<{ ok: boolean; id: number; decision: Decision }>(
		`/peer-sync/items/${itemId}/decision`,
		{ method: 'POST', body: JSON.stringify({ decision }) }
	);
}

export async function applyItem(itemId: number) {
	return apiFetch<{ ok: boolean; id: number; decision: Decision }>(
		`/peer-sync/items/${itemId}/apply`,
		{ method: 'POST' }
	);
}
