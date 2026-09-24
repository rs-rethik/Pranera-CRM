import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import frappeui from 'frappe-ui/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Everything the built app serves lives under this prefix (Frappe's asset URL
// for pranera_crm/public/frontend). The SPA itself is mounted at /deal_wizard/.
const ASSET_BASE = '/assets/pranera_crm/frontend/'
const SCOPE = '/deal_wizard/'

// https://vitejs.dev/config/
export default defineConfig({
	plugins: [
		// Same setup as Frappe CRM: dev proxy to the bench webserver, Jinja boot
		// data (csrf_token etc.) injected into the built index.html, and the build
		// written to pranera_crm/public/frontend + copied to www/deal_wizard.html.
		frappeui({
			frappeProxy: true,
			lucideIcons: true,
			jinjaBootData: true,
			buildConfig: {
				indexHtmlPath: '../pranera_crm/www/deal_wizard.html',
				emptyOutDir: true,
				sourcemap: false,
			},
		}),
		vue(),
		VitePWA({
			// Hand-written worker (src/sw.js): NetworkOnly for /api, NetworkFirst for
			// navigations, and precache of hashed static assets only.
			strategies: 'injectManifest',
			srcDir: 'src',
			filename: 'sw.js',
			// registered manually from main.js at /deal_wizard/sw.js (see pranera_crm/sw.py)
			injectRegister: false,
			registerType: 'autoUpdate',
			manifestFilename: 'manifest.webmanifest',
			manifest: {
				id: SCOPE,
				name: 'Pranera CRM',
				short_name: 'Pranera CRM',
				description: 'Convert Frappe CRM leads to deals, step by step.',
				display: 'standalone',
				scope: SCOPE,
				start_url: SCOPE,
				theme_color: '#4f46e5',
				background_color: '#ffffff',
				lang: 'en',
				categories: ['business', 'productivity'],
				icons: [
					{
						src: `${ASSET_BASE}icons/icon-192.png`,
						sizes: '192x192',
						type: 'image/png',
						purpose: 'any',
					},
					{
						src: `${ASSET_BASE}icons/icon-512.png`,
						sizes: '512x512',
						type: 'image/png',
						purpose: 'any',
					},
					{
						src: `${ASSET_BASE}icons/icon-192-maskable.png`,
						sizes: '192x192',
						type: 'image/png',
						purpose: 'maskable',
					},
					{
						src: `${ASSET_BASE}icons/icon-512-maskable.png`,
						sizes: '512x512',
						type: 'image/png',
						purpose: 'maskable',
					},
				],
			},
			injectManifest: {
				rollupFormat: 'iife',
				// Hashed static assets only. index.html is deliberately NOT precached:
				// it embeds a per-session CSRF token that must always come from the network.
				globPatterns: ['assets/**/*.{js,css,woff,woff2}', 'icons/*.png'],
				globIgnores: ['**/*.map', '**/index.html'],
				// The worker is served from /deal_wizard/, so relative precache URLs must be
				// rewritten to the real asset location.
				modifyURLPrefix: { '': ASSET_BASE },
				maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
			},
			devOptions: { enabled: false },
		}),
	],
	resolve: {
		alias: {
			'@': path.resolve(import.meta.dirname, 'src'),
		},
		dedupe: ['vue', 'vue-router', 'frappe-ui'],
	},
	optimizeDeps: {
		include: ['feather-icons', 'tailwind.config.js', 'interactjs'],
	},
})
