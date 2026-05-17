import { writable, derived } from 'svelte/store';

interface User {
	id: number;
	username: string;
	is_admin: boolean;
	is_active: boolean;
	created_at: string;
}

interface AuthState {
	user: User | null;
	token: string | null;
	loading: boolean;
}

function createAuthStore() {
	const { subscribe, set, update } = writable<AuthState>({
		user: null,
		token: null,
		loading: true
	});

	return {
		subscribe,
		setToken(token: string) {
			localStorage.setItem('borgos_token', token);
			update((s) => ({ ...s, token }));
		},
		setUser(user: User) {
			update((s) => ({ ...s, user, loading: false }));
		},
		logout() {
			localStorage.removeItem('borgos_token');
			set({ user: null, token: null, loading: false });
		},
		setLoading(loading: boolean) {
			update((s) => ({ ...s, loading }));
		},
		getToken(): string | null {
			if (typeof window === 'undefined') return null;
			return localStorage.getItem('borgos_token');
		}
	};
}

export const authStore = createAuthStore();
export const isAuthenticated = derived(authStore, ($auth) => !!$auth.user && !$auth.loading);
export const currentUser = derived(authStore, ($auth) => $auth.user);
