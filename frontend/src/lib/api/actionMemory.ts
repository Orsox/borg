import { apiFetch } from './client';

// --- Types ---
export interface ActionMemory {
	id: number;
	title: string;
	description: string;
	action_type: string;
	tools_used: string[];
	status: string;
	is_archived: boolean;
	duration_ms: number | null;
	output_path: string | null;
	metadata: Record<string, unknown>;
	tags: string[];
	created_at: string;
	updated_at: string;
}

export interface ActionMemoryListItem {
	id: number;
	title: string;
	action_type: string;
	status: string;
	tools_used: string[];
	tags: string[];
	created_at: string;
	updated_at: string;
}

export interface PaginatedActionMemories {
	items: ActionMemoryListItem[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface ActionMemoryStats {
	total: number;
	success_count: number;
	failed_count: number;
	in_progress_count: number;
	action_types: Array<{ type: string; count: number }>;
}

// --- API functions ---
export async function createActionMemory(
	title: string,
	description = '',
	action_type = 'general',
	tools_used: string[] = [],
	status = 'success',
	duration_ms: number | null = null,
	output_path: string | null = null,
	metadata: Record<string, unknown> = {},
	tags: string[] = [],
): Promise<ActionMemory> {
	return apiFetch<ActionMemory>('/brain/actions', {
		method: 'POST',
		body: JSON.stringify({
			title,
			description,
			action_type,
			tools_used,
			status,
			duration_ms,
			output_path,
			metadata,
			tags,
		}),
	});
}

export async function listActionMemories(
	page = 1,
	size = 20,
	search?: string,
	action_type?: string,
	status?: string,
	archived = false,
): Promise<PaginatedActionMemories> {
	const params = new URLSearchParams({ page: String(page), size: String(size) });
	if (search) params.set('search', search);
	if (action_type) params.set('action_type', action_type);
	if (status) params.set('status', status);
	if (archived) params.set('archived', 'true');
	return apiFetch<PaginatedActionMemories>(`/brain/actions?${params}`);
}

export async function getActionMemory(id: number): Promise<ActionMemory> {
	return apiFetch<ActionMemory>(`/brain/actions/${id}`);
}

export async function updateActionMemory(
	id: number,
	title?: string,
	description?: string,
	action_type?: string,
	tools_used?: string[],
	status?: string,
	duration_ms?: number | null,
	output_path?: string | null,
	metadata?: Record<string, unknown>,
	tags?: string[],
): Promise<ActionMemory> {
	const body: Record<string, unknown> = {};
	if (title !== undefined) body.title = title;
	if (description !== undefined) body.description = description;
	if (action_type !== undefined) body.action_type = action_type;
	if (tools_used !== undefined) body.tools_used = tools_used;
	if (status !== undefined) body.status = status;
	if (duration_ms !== undefined) body.duration_ms = duration_ms;
	if (output_path !== undefined) body.output_path = output_path;
	if (metadata !== undefined) body.metadata = metadata;
	if (tags !== undefined) body.tags = tags;
	return apiFetch<ActionMemory>(`/brain/actions/${id}`, {
		method: 'PUT',
		body: JSON.stringify(body),
	});
}

export async function archiveActionMemory(id: number): Promise<ActionMemory> {
	return apiFetch<ActionMemory>(`/brain/actions/${id}`, { method: 'DELETE' });
}

export async function getActionMemoryStats(): Promise<ActionMemoryStats> {
	return apiFetch<ActionMemoryStats>('/brain/actions/stats');
}
