import { apiFetch } from './client';

// --- Types ---
export interface Persona {
	key: string;
	display_name: string;
	color: string;
}

export interface MeetingTurn {
	speaker: string; // persona key, or "orsox"
	display_name: string;
	content: string;
	ts: string;
}

export type MeetingStatus = 'running' | 'done' | 'error';

export interface MeetingSession {
	id: string;
	theme: string;
	rounds_total: number;
	rounds_done: number;
	status: MeetingStatus;
	speaking: string | null;
	error: string | null;
	transcript: MeetingTurn[];
}

// Default round budget when the /meeting codeword is omitted.
export const DEFAULT_ROUNDS = 3;

// --- API functions ---
export async function getPersonas(): Promise<Persona[]> {
	return apiFetch<Persona[]>('/meeting/personas');
}

export async function startMeeting(theme: string, rounds: number): Promise<MeetingSession> {
	return apiFetch<MeetingSession>('/meeting/sessions', {
		method: 'POST',
		body: JSON.stringify({ theme, rounds })
	});
}

export async function getSession(id: string): Promise<MeetingSession> {
	return apiFetch<MeetingSession>(`/meeting/sessions/${id}`);
}

export async function sendMessage(
	id: string,
	message: string,
	rounds: number
): Promise<MeetingSession> {
	return apiFetch<MeetingSession>(`/meeting/sessions/${id}/message`, {
		method: 'POST',
		body: JSON.stringify({ message, rounds })
	});
}

// --- Input parsing ---
export interface ParsedInput {
	rounds: number;
	text: string;
}

/**
 * Parse the input bar. `/meeting <N> <theme>` sets the round budget; anything
 * else uses the default. Returns null when there is no usable text.
 */
export function parseMeetingInput(raw: string): ParsedInput | null {
	const trimmed = raw.trim();
	if (!trimmed) return null;

	const match = trimmed.match(/^\/meeting\s+(\d+)\s+([\s\S]+)$/i);
	if (match) {
		return { rounds: Math.max(1, Math.min(12, parseInt(match[1], 10))), text: match[2].trim() };
	}
	// Bare "/meeting <theme>" (no number) → default rounds.
	const noNum = trimmed.match(/^\/meeting\s+([\s\S]+)$/i);
	if (noNum) {
		return { rounds: DEFAULT_ROUNDS, text: noNum[1].trim() };
	}
	return { rounds: DEFAULT_ROUNDS, text: trimmed };
}
