import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
	history: createWebHistory('/deal_wizard/'),
	routes: [
		{ path: '/', name: 'Home', component: () => import('@/pages/Home.vue') },
		// shown inside CRM by pranera_crm/public/js/crm_sidebar_ext.js
		{ path: '/reports', name: 'Reports', component: () => import('@/pages/Reports.vue') },
		{
			path: '/reports/:reportName',
			name: 'Report',
			component: () => import('@/pages/Report.vue'),
			props: true,
		},
		{
			path: '/:name',
			name: 'Wizard',
			component: () => import('@/pages/Wizard.vue'),
			props: true,
		},
	],
	scrollBehavior: () => ({ top: 0 }),
})

// inside CRM's panel, tell CRM which page is shown so it can keep it in its URL
router.afterEach((to) => {
	if (window.parent !== window) {
		window.parent.postMessage(
			{ type: 'pranera:panel-route', path: to.path },
			window.location.origin
		)
	}
})

export default router
