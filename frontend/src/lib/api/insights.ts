import { apiFetch } from './client';

// --- Types ---
export interface Insight {
	id: number;
	dedup_key: string;
	category: string;
	workflow: string | null;
	summary: string;
	recommendation: string;
	evidence_action_ids: number[];
	occurrences: number;
	status: string;
	first_seen: string | null;
	last_seen: string | null;
	created_at: string;
	updated_at: string;
}

export interface PaginatedInsights {
	items: Insight[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface GenerateResult {
	created: number;
	updated: number;
	total_open: number;
}

// --- API functions ---
export async function listInsights(
	status = 'open',
	page = 1,
	size = 20,
): Promise<PaginatedInsights> {
	const params = new URLSearchParams({
		status,
		page: String(page),
		size: String(size),
	});
	return apiFetch<PaginatedInsights>(`/brain/insights?${params}`);
}

export async function getTopInsights(limit = 3): Promise<Insight[]> {
	return apiFetch<Insight[]>(`/brain/insights/top?limit=${limit}`);
}

export async function acknowledgeInsight(id: number): Promise<Insight> {
	return apiFetch<Insight>(`/brain/insights/${id}/acknowledge`, { method: 'POST' });
}

export async function resolveInsight(id: number): Promise<Insight> {
	return apiFetch<Insight>(`/brain/insights/${id}/resolve`, { method: 'POST' });
}

export async function generateInsights(days = 14): Promise<GenerateResult> {
	return apiFetch<GenerateResult>(`/brain/insights/generate?days=${days}`, {
		method: 'POST',
	});
}
