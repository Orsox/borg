import { apiFetch } from './client';

export interface Draft {
	filename: string;
	type: string;
	source_id: string;
	subject: string;
	created: string;
	status: string;
	content_preview: string;
}

export interface Habit {
	pillar: string;
	description: string;
	checked: boolean;
	auto_detectable: boolean;
}

export interface SearchResult {
	path: string;
	content: string;
	score: number;
}

export interface HeartbeatState {
	timestamp: string;
	jira_count: number;
	gitlab_projects: string[];
	teams_count: number;
	polarion_count: number;
}

export async function listDrafts(): Promise<Draft[]> {
	return apiFetch<Draft[]>('/vault/drafts');
}

export async function getDraft(filename: string): Promise<{ content: string }> {
	return apiFetch<{ content: string }>(`/vault/drafts/${encodeURIComponent(filename)}`);
}

export async function expireDraft(filename: string): Promise<{ ok: boolean }> {
	return apiFetch<{ ok: boolean }>(`/vault/drafts/${encodeURIComponent(filename)}/expire`, {
		method: 'POST',
	});
}

export async function getHabits(): Promise<Habit[]> {
	return apiFetch<Habit[]>('/vault/habits');
}

export async function searchVault(q: string, topK = 5): Promise<SearchResult[]> {
	const params = new URLSearchParams({ q, top_k: String(topK) });
	return apiFetch<SearchResult[]>(`/vault/search?${params}`);
}

export async function getHeartbeatStatus(): Promise<HeartbeatState | null> {
	try {
		return await apiFetch<HeartbeatState>('/vault/heartbeat');
	} catch {
		return null;
	}
}
