import './index.css'

import { createApp } from 'vue'
import { FrappeUI, frappeRequest, setConfig } from 'frappe-ui'
import App from './App.vue'
import router from './router'
import { redirectToLogin } from './lib/api'
import { applySiteProperties } from './lib/site'
import translationPlugin, { setTranslations } from './translation'

function registerServiceWorker() {
  if (!('serviceWorker' in navigator) || import.meta.env.DEV) return

  const register = () =>
    // Served at /deal_wizard/sw.js by pranera_crm.sw so the default scope is
    // /deal_wizard/ (and the Service-Worker-Allowed header is sent as well).
    navigator.serviceWorker
      .register('/deal_wizard/sw.js', { scope: '/deal_wizard/' })
      .catch((err) => console.warn('Pranera CRM: service worker registration failed', err))

  if (document.readyState === 'complete') register()
  else window.addEventListener('load', register, { once: true })
}

async function loadDevBoot() {
  // Production gets boot data (csrf_token, user…) injected by Jinja into the
  // page. The Vite dev server has no Jinja, so ask Frappe for it instead.
  const values = await frappeRequest({ url: '/api/method/pranera_crm.www.deal_wizard.get_context_for_dev' })
  for (const key in values) window[key] = values[key]
}

async function boot() {
  if (import.meta.env.DEV) {
    try {
      await loadDevBoot()
    } catch (err) {
      document.body.innerHTML = `<pre style="padding:16px">Could not load boot data: ${err?.message}\nIs developer_mode enabled on the site (bench set-config developer_mode 1)?</pre>`
      return
    }
  }

  // Not logged in (or the boot data is missing): go to login and come straight back.
  if (!window.pranera_user || window.pranera_user === 'Guest') {
    redirectToLogin()
    return
  }

  // language, direction, tab title and favicon follow the site (as in CRM)
  setTranslations(window.translated_messages)
  applySiteProperties()

  setConfig('resourceFetcher', frappeRequest)
  const app = createApp(App)
  app.use(translationPlugin)
  // realtime isn't used here; skip frappe-ui's default socket.io connection
  app.use(FrappeUI, { socketio: false })
  app.use(router)
  app.mount('#app')

  registerServiceWorker()
}

boot()
