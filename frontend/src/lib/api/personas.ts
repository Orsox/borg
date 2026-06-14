/**
 * API client for persona management endpoints.
 *
 * Mirrors the /api/personas CRUD routes defined in backend/app/personas/router.py.
 */

import { apiFetch } from './client';

const BASE = '/personas';

// ── Types ──────────────────────────────────────────────────────

export interface LlmConfig {
	base_url: string;
	model_id: string;
	context_window: number;
	max_tokens: number;
	temperature: number;
}

export interface DiscordConfig {
	enabled: boolean;
	token: string | null;
	channel_id: number | null;
	allowed_user_ids: string | null;
	prefix: string;
	mention_prefix: string;
}

/** Lightweight persona for list views (excludes system_prompt). */
export interface PersonaListItem {
	id: number;
	key: string;
	display_name: string;
	color: string | null;
	llm_model_id: string;
	discord_enabled: boolean;
	is_active: boolean;
	include_in_meetings: boolean;
	created_at: string;
	updated_at: string;
}

/** Full persona detail (matches PersonaResponse from backend). */
export interface PersonaDetail {
	id: number;
	key: string;
	display_name: string;
	color: string | null;
	system_prompt: string | null;
	llm: LlmConfig;
	discord: DiscordConfig;
	is_active: boolean;
	include_in_meetings: boolean;
	created_at: string;
	updated_at: string;
}

// ── API functions ──────────────────────────────────────────────

export async function listPersonas(): Promise<{ items: PersonaListItem[]; total: number }> {
	return apiFetch(`${BASE}`);
}

export async function getPersona(id: number): Promise<PersonaDetail> {
	return apiFetch(`${BASE}/${id}`);
}

export async function createPersona(body: {
	key: string;
	display_name: string;
	color?: string | null;
	system_prompt?: string | null;
	llm?: Partial<LlmConfig>;
	discord?: Partial<DiscordConfig>;
	is_active?: boolean;
	include_in_meetings?: boolean;
}): Promise<PersonaDetail> {
	return apiFetch(`${BASE}`, {
		method: 'POST',
		body: JSON.stringify(body),
	});
}

export async function updatePersona(
	id: number,
	body: Partial<{
		key: string;
		display_name: string;
		color: string | null;
		system_prompt: string | null;
		llm: LlmConfig;
		discord: DiscordConfig;
		is_active: boolean;
		include_in_meetings: boolean;
	}>,
): Promise<PersonaDetail> {
	return apiFetch(`${BASE}/${id}`, {
		method: 'PUT',
		body: JSON.stringify(body),
	});
}

export async function deletePersona(id: number): Promise<void> {
	return apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
}
