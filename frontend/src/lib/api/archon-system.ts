import { apiFetch } from './client';

export interface ArchonSystemHealth {
	online: boolean;
	archon_url: string;
	version: string | null;
	adapter: string | null;
	is_docker: boolean;
	active_platforms: string[];
	running_workflows: number;
	concurrency: { active: number; queued_total: number; max_concurrent: number } | null;
	checked_at: string | null;
	cached: boolean;
}

export interface ArchonRun {
	id: string;
	workflow_name: string;
	status: string;
	user_message: string | null;
	started_at: string | null;
	last_activity_at: string | null;
	completed_at: string | null;
	codebase_name: string | null;
	working_path: string | null;
}

export interface ArchonCodebase {
	id: string;
	name: string;
	repository_url: string | null;
	default_branch: string | null;
	ai_assistant_type: string | null;
}

export interface ArchonWorkflow {
	name: string;
	description: string | null;
	provider: string | null;
	source: string;
}

export async function getArchonSystemHealth(): Promise<ArchonSystemHealth> {
	return apiFetch<ArchonSystemHealth>('/archon-system/health');
}

export async function listArchonRuns(params: { status?: string; limit?: number } = {}) {
	const qs = new URLSearchParams();
	if (params.status) qs.set('status', params.status);
	if (params.limit) qs.set('limit', String(params.limit));
	return apiFetch<{ items: ArchonRun[]; total: number }>(`/archon-system/runs?${qs}`);
}

export async function listArchonCodebases() {
	return apiFetch<{ items: ArchonCodebase[]; total: number }>('/archon-system/codebases');
}

export async function listArchonWorkflows() {
	return apiFetch<{ items: ArchonWorkflow[]; total: number }>('/archon-system/workflows');
}
