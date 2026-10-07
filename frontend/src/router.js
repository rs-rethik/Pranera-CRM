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

export default router
