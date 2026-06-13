import { apiFetch } from './client';

// --- Types ---
export interface ObservabilityStatus {
	configured: boolean;
	tracing_enabled: boolean;
	reachable: boolean;
	host: string;
	ui_url: string;
	error: string | null;
}

export interface TraceSummary {
	id: string;
	timestamp: string | null;
	name: string | null;
	persona: string | null;
	session_id: string | null;
	tags: string[];
	latency_ms: number | null;
	level: string | null;
	input_preview: string | null;
	output_preview: string | null;
	ui_url: string | null;
}

export interface PaginatedTraces {
	items: TraceSummary[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface ObservationSummary {
	id: string;
	type: string | null;
	name: string | null;
	start_time: string | null;
	end_time: string | null;
	level: string | null;
	status_message: string | null;
	model: string | null;
	usage: Record<string, number>;
	input: unknown;
	output: unknown;
	parent_observation_id: string | null;
}

export interface TraceDetail extends TraceSummary {
	input: unknown;
	output: unknown;
	metadata: unknown;
	observations: ObservationSummary[];
}

// --- API functions ---
export async function getObservabilityStatus(): Promise<ObservabilityStatus> {
	return apiFetch<ObservabilityStatus>('/observability/status');
}

export async function listTraces(
	opts: { page?: number; size?: number; persona?: string; tag?: string; sessionId?: string } = {},
): Promise<PaginatedTraces> {
	const params = new URLSearchParams({
		page: String(opts.page ?? 1),
		size: String(opts.size ?? 25),
	});
	if (opts.persona) params.set('persona', opts.persona);
	if (opts.tag) params.set('tag', opts.tag);
	if (opts.sessionId) params.set('session_id', opts.sessionId);
	return apiFetch<PaginatedTraces>(`/observability/traces?${params}`);
}

export async function getTrace(id: string): Promise<TraceDetail> {
	return apiFetch<TraceDetail>(`/observability/traces/${encodeURIComponent(id)}`);
}
