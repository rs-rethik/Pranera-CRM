/* Pranera CRM service worker (built with vite-plugin-pwa / injectManifest).
 *
 * Served at /deal_wizard/sw.js (see pranera_crm/sw.py) so its scope is
 * /deal_wizard/ and it never touches Frappe CRM's own worker under /crm/.
 */
import { clientsClaim, setCacheNameDetails } from 'workbox-core'
import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'
import { registerRoute } from 'workbox-routing'
import { NetworkFirst, NetworkOnly } from 'workbox-strategies'

// Caches are per-origin, not per-scope: use our own namespace so we neither
// reuse nor clean up the CRM worker's caches.
setCacheNameDetails({ prefix: 'pranera-crm' })

self.skipWaiting()
clientsClaim()
cleanupOutdatedCaches()

// Hashed static assets only. index.html is deliberately not precached: it
// embeds the session's CSRF token, and a stale copy would break every API call.
precacheAndRoute(self.__WB_MANIFEST)

// API traffic always goes to the network and is never cached or replayed,
// whatever the method. In particular the conversion request is not queued
// offline: replaying it could create duplicate contacts and organizations.
const isApi = ({ url }) => url.pathname.startsWith('/api/')
for (const method of ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']) {
  registerRoute(isApi, new NetworkOnly(), method)
}

// Page navigations: network first, so the boot data (CSRF token, user) is
// always fresh; the last good copy is only a fallback for opening the app offline.
const SHELL_KEY = new URL('/deal_wizard/', self.location.origin).href
registerRoute(
  ({ request, url }) => request.mode === 'navigate' && url.pathname.startsWith('/deal_wizard'),
  new NetworkFirst({
    cacheName: 'pranera-crm-pages',
    networkTimeoutSeconds: 5,
    plugins: [
      {
        // every wizard URL serves the same shell, so keep a single copy
        cacheKeyWillBeUsed: async () => SHELL_KEY,
        // never keep a redirect (e.g. to /login) or an error page as the fallback
        cacheWillUpdate: async ({ response }) =>
          response && response.status === 200 && !response.redirected ? response : null,
      },
    ],
  }),
)
