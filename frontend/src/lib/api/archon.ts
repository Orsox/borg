import { apiFetch } from './client';

export interface Asset {
	id: number;
	name: string;
	type: string;
	description: string | null;
	tags: string[];
	file_path: string;
	raw_content: string;
	last_scanned: string;
	is_favorite: boolean;
	created_at: string;
}

export interface PaginatedAssets {
	items: Asset[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface CopyHistoryItem {
	id: number;
	asset_id: number;
	asset_name: string;
	source_path: string;
	destination_path: string;
	copied_at: string;
}

export async function scanAssets() {
	return apiFetch<{ count: number; scanned_at: string }>('/archon/scan', { method: 'POST' });
}

export async function listAssets(params: {
	page?: number;
	size?: number;
	type?: string;
	search?: string;
	tags?: string;
	favorites?: boolean;
} = {}): Promise<PaginatedAssets> {
	const qs = new URLSearchParams();
	if (params.page) qs.set('page', String(params.page));
	if (params.size) qs.set('size', String(params.size));
	if (params.type) qs.set('type', params.type);
	if (params.search) qs.set('search', params.search);
	if (params.tags) qs.set('tags', params.tags);
	if (params.favorites) qs.set('favorites', 'true');
	return apiFetch<PaginatedAssets>(`/archon/assets?${qs}`);
}

export async function getAsset(id: number): Promise<Asset> {
	return apiFetch<Asset>(`/archon/assets/${id}`);
}

export async function copyAsset(id: number) {
	return apiFetch<{ source_path: string; destination_path: string; copied_at: string }>(
		`/archon/assets/${id}/copy`,
		{ method: 'POST' }
	);
}

export async function toggleFavorite(id: number) {
	return apiFetch<{ id: number; is_favorite: boolean }>(`/archon/assets/${id}/favorite`, {
		method: 'POST'
	});
}

export async function getCopyHistory(): Promise<CopyHistoryItem[]> {
	return apiFetch<CopyHistoryItem[]>('/archon/copy-history');
}
