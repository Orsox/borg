import { apiFetch } from './client';

// --- Types ---
export interface Note {
	id: number;
	title: string;
	content: string;
	tags: string[];
	is_archived: boolean;
	created_at: string;
	updated_at: string;
}

export interface NoteListItem {
	id: number;
	title: string;
	tags: string[];
	created_at: string;
	updated_at: string;
}

export interface PaginatedNotes {
	items: NoteListItem[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface BacklinkItem {
	id: number;
	title: string;
	updated_at: string;
}

export interface GraphNode {
	id: number;
	title: string;
	tags: string[];
}

export interface GraphEdge {
	source: number;
	target: number;
}

export interface KnowledgeGraph {
	nodes: GraphNode[];
	edges: GraphEdge[];
}

// --- API functions ---
export async function createNote(title: string, content: string = '', tags: string[] = []): Promise<Note> {
	return apiFetch<Note>('/brain/notes', {
		method: 'POST',
		body: JSON.stringify({ title, content, tags }),
	});
}

export async function listNotes(
	page = 1,
	size = 20,
	search?: string,
	tags?: string,
	archived = false,
): Promise<PaginatedNotes> {
	const params = new URLSearchParams({ page: String(page), size: String(size) });
	if (search) params.set('search', search);
	if (tags) params.set('tags', tags);
	if (archived) params.set('archived', 'true');
	return apiFetch<PaginatedNotes>(`/brain/notes?${params}`);
}

export async function getNote(id: number): Promise<Note> {
	return apiFetch<Note>(`/brain/notes/${id}`);
}

export async function updateNote(
	id: number,
	title?: string,
	content?: string,
	tags?: string[],
): Promise<Note> {
	const body: Record<string, unknown> = {};
	if (title !== undefined) body.title = title;
	if (content !== undefined) body.content = content;
	if (tags !== undefined) body.tags = tags;
	return apiFetch<Note>(`/brain/notes/${id}`, {
		method: 'PUT',
		body: JSON.stringify(body),
	});
}

export async function archiveNote(id: number): Promise<Note> {
	return apiFetch<Note>(`/brain/notes/${id}`, { method: 'DELETE' });
}

export async function getBacklinks(id: number): Promise<BacklinkItem[]> {
	return apiFetch<BacklinkItem[]>(`/brain/notes/${id}/backlinks`);
}

export async function getKnowledgeGraph(): Promise<KnowledgeGraph> {
	return apiFetch<KnowledgeGraph>('/brain/graph');
}

// --- Combined graph (vault + DB notes + action memory) ---
export type GraphSource = 'vault' | 'note' | 'action';

export interface CombinedGraphNode {
	id: string;
	title: string;
	source: GraphSource;
	kind: string;
	tags: string[];
	backlink_count: number;
	ref: string;
}

export interface CombinedGraphEdge {
	source: string;
	target: string;
}

export interface CombinedGraph {
	nodes: CombinedGraphNode[];
	edges: CombinedGraphEdge[];
}

export async function getCombinedGraph(linkTags = false): Promise<CombinedGraph> {
	const params = linkTags ? '?link_tags=true' : '';
	return apiFetch<CombinedGraph>(`/brain/graph/combined${params}`);
}

// --- Federated search (vault + DB notes + action memory) ---
export interface BrainSearchResult {
	id: string;
	title: string;
	source: GraphSource;
	kind: string;
	tags: string[];
	ref: string;
	snippet: string;
	score: number;
	updated_at: string | null;
}

export interface BrainSearchResponse {
	query: string;
	sources: string[];
	results: BrainSearchResult[];
}

export async function searchBrain(
	q: string,
	sources?: GraphSource[],
	limit = 20,
): Promise<BrainSearchResponse> {
	const params = new URLSearchParams({ q, limit: String(limit) });
	if (sources?.length) params.set('sources', sources.join(','));
	return apiFetch<BrainSearchResponse>(`/brain/search?${params}`);
}

// --- Per-item relations (links, backlinks, shared-tag neighbors) ---
export interface RelatedItem {
	id: string;
	title: string;
	source: GraphSource;
	kind: string;
	tags: string[];
	ref: string;
}

export interface ItemRelations {
	id: string;
	links: RelatedItem[];
	backlinks: RelatedItem[];
	related: RelatedItem[];
}

export async function getItemRelations(id: string): Promise<ItemRelations> {
	return apiFetch<ItemRelations>(`/brain/related?id=${encodeURIComponent(id)}`);
}
