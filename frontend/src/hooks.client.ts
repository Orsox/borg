import { getMe } from '$lib/api/client';
import { authStore } from '$lib/stores/auth';

export async function init() {
	const token = authStore.getToken();
	if (token) {
		try {
			authStore.setToken(token);
			const user = await getMe();
			authStore.setUser(user);
		} catch {
			authStore.logout();
		}
	} else {
		authStore.setLoading(false);
	}
}
