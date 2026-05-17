import { apiFetch } from './client';

// --- Types ---
export interface Task {
	id: number;
	name: string;
	description: string | null;
	task_type: string;
	schedule: string | null;
	command: string | null;
	archon_workflow_name: string | null;
	is_enabled: boolean;
	tags: string[];
	retry_max: number;
	retry_delay: number;
	timeout: number;
	created_at: string;
	updated_at: string;
}

export interface TaskListItem {
	id: number;
	name: string;
	description: string | null;
	task_type: string;
	schedule: string | null;
	is_enabled: boolean;
	tags: string[];
	created_at: string;
	updated_at: string;
}

export interface PaginatedTasks {
	items: TaskListItem[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface TaskRun {
	id: number;
	task_id: number;
	started_at: string;
	finished_at: string | null;
	status: string;
	exit_code: number | null;
	stdout: string | null;
	stderr: string | null;
	duration_ms: number | null;
}

// --- API functions ---
export async function createTask(
	name: string,
	task_type: string = 'shell',
	schedule: string | null = null,
	command: string | null = null,
	archon_workflow_name: string | null = null,
	description: string | null = null,
	tags: string[] = [],
	retry_max = 0,
	retry_delay = 60,
	timeout = 300,
): Promise<Task> {
	return apiFetch<Task>('/tasks', {
		method: 'POST',
		body: JSON.stringify({
			name, task_type, schedule, command,
			archon_workflow_name, description, tags,
			retry_max, retry_delay, timeout,
		}),
	});
}

export async function listTasks(
	page = 1,
	size = 20,
	search?: string,
	tags?: string,
	status?: string,
): Promise<PaginatedTasks> {
	const params = new URLSearchParams({ page: String(page), size: String(size) });
	if (search) params.set('search', search);
	if (tags) params.set('tags', tags);
	if (status) params.set('status', status);
	return apiFetch<PaginatedTasks>(`/tasks?${params}`);
}

export async function getTask(id: number): Promise<Task> {
	return apiFetch<Task>(`/tasks/${id}`);
}

export async function updateTask(
	id: number,
	updates: Record<string, unknown>,
): Promise<Task> {
	return apiFetch<Task>(`/tasks/${id}`, {
		method: 'PUT',
		body: JSON.stringify(updates),
	});
}

export async function deleteTask(id: number): Promise<void> {
	return apiFetch<void>(`/tasks/${id}`, { method: 'DELETE' });
}

export async function toggleTask(id: number): Promise<{ id: number; is_enabled: boolean }> {
	return apiFetch<{ id: number; is_enabled: boolean }>(`/tasks/${id}/toggle`, { method: 'POST' });
}

export async function runTaskNow(id: number): Promise<{ task_run_id: number; message: string }> {
	return apiFetch<{ task_run_id: number; message: string }>(`/tasks/${id}/run`, { method: 'POST' });
}

export async function getTaskRuns(
	taskId: number,
	page = 1,
	size = 20,
): Promise<{ items: TaskRun[]; total: number; page: number; size: number; pages: number }> {
	const params = new URLSearchParams({ page: String(page), size: String(size) });
	return apiFetch(`/tasks/${taskId}/runs?${params}`);
}
