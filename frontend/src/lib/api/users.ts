import { apiFetch } from '$lib/api/client';

const BASE = '/users';

export interface UserListItem {
	id: number;
	username: string;
	is_admin: boolean;
	is_active: boolean;
	created_at: string;
}

export interface UserListResponse {
	items: UserListItem[];
	total: number;
}

export async function listUsers(): Promise<UserListResponse> {
	return apiFetch<UserListResponse>(BASE);
}

export async function createUser(
	username: string,
	password: string,
	is_admin = false
): Promise<UserListItem> {
	return apiFetch<UserListItem>(BASE, {
		method: 'POST',
		body: JSON.stringify({ username, password, is_admin }),
	});
}

export async function updateUserUsername(
	userId: number,
	username: string
): Promise<UserListItem> {
	return apiFetch<UserListItem>(`${BASE}/${userId}`, {
		method: 'PUT',
		body: JSON.stringify({ username }),
	});
}

export async function adminSetPassword(
	userId: number,
	new_password: string
): Promise<void> {
	return apiFetch<void>(`${BASE}/${userId}/set-password`, {
		method: 'POST',
		body: JSON.stringify({ new_password }),
	});
}

export async function deactivateUser(userId: number): Promise<void> {
	return apiFetch<void>(`${BASE}/${userId}`, { method: 'DELETE' });
}

export async function changeMyPassword(
	current_password: string,
	new_password: string
): Promise<void> {
	return apiFetch<void>('/auth/me/change-password', {
		method: 'POST',
		body: JSON.stringify({ current_password, new_password }),
	});
}

export async function updateMyUsername(username: string): Promise<UserListItem> {
	return apiFetch<UserListItem>('/auth/me', {
		method: 'PUT',
		body: JSON.stringify({ username }),
	});
}
