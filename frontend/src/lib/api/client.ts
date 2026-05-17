const API_BASE = '/api';

function getToken(): string | null {
	if (typeof window === 'undefined') return null;
	return localStorage.getItem('borgos_token');
}

interface FetchOptions extends RequestInit {
	skipAuth?: boolean;
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
	const { skipAuth = false, ...init } = options;
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(init.headers as Record<string, string>)
	};

	if (!skipAuth) {
		const token = getToken();
		if (token) headers['Authorization'] = `Bearer ${token}`;
	}

	const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

	if (!res.ok) {
		let errMsg = `HTTP ${res.status}`;
		try {
			const body = await res.json();
			errMsg = body.error ?? body.detail ?? errMsg;
		} catch {}
		throw new Error(errMsg);
	}

	// 204 No Content or empty body — nothing to parse
	if (res.status === 204 || res.headers.get('content-length') === '0') {
		return null as T;
	}

	return res.json();
}

export async function login(username: string, password: string) {
	const params = new URLSearchParams({ username, password });
	const res = await fetch(`${API_BASE}/auth/token`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
		body: params.toString()
	});

	if (!res.ok) {
		const body = await res.json().catch(() => ({ error: 'Login failed' }));
		throw new Error(body.error ?? 'Login failed');
	}

	return res.json() as Promise<{ access_token: string; refresh_token: string; token_type: string }>;
}

export async function getMe() {
	return apiFetch<{ id: number; username: string; is_admin: boolean; is_active: boolean; created_at: string }>('/auth/me');
}

export async function getHealth() {
	return apiFetch<{ status: string; uptime_seconds: number; modules: Record<string, string> }>('/health', { skipAuth: true });
}
