/* Pranera CRM service worker (built with vite-plugin-pwa / injectManifest).
 *
 * Served at /deal_wizard/sw.js (see pranera_crm/sw.py) so its scope is
 * /deal_wizard/ and it never touches Frappe CRM's own worker under /crm/.
 */
import { clientsClaim, setCacheNameDetails } from 'workbox-core'
import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'
import { registerRoute } from 'workbox-routing'
import { NetworkFirst, NetworkOnly } from 'workbox-strategies'

setCacheNameDetails({ prefix: 'pranera-crm' })

self.skipWaiting()
clientsClaim()
cleanupOutdatedCaches()

precacheAndRoute(self.__WB_MANIFEST)

const isApi = ({ url }) => url.pathname.startsWith('/api/')
for (const method of ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']) {
  registerRoute(isApi, new NetworkOnly(), method)
}

const SHELL_KEY = new URL('/deal_wizard/', self.location.origin).href
registerRoute(
  ({ request, url }) => request.mode === 'navigate' && url.pathname.startsWith('/deal_wizard'),
  new NetworkFirst({
    cacheName: 'pranera-crm-pages',
    networkTimeoutSeconds: 5,
    plugins: [
      {
        cacheKeyWillBeUsed: async () => SHELL_KEY,
        cacheWillUpdate: async ({ response }) =>
          response && response.status === 200 && !response.redirected ? response : null,
      },
    ],
  }),
)
