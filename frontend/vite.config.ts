import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		port: 5173,
		proxy: {
			'/api': {
				// Override when :8000 is taken (e.g. by the LM Studio container)
				target: process.env.BORG_BACKEND_URL ?? 'http://localhost:8000',
				changeOrigin: true
			}
		}
	}
});
