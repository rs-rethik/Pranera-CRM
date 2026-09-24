import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory('/deal_wizard/'),
  routes: [
    { path: '/', name: 'Home', component: () => import('@/pages/Home.vue') },
    { path: '/:name', name: 'Wizard', component: () => import('@/pages/Wizard.vue'), props: true },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

export default router
