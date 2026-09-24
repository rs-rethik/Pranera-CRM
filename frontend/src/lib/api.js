import { call } from 'frappe-ui'
import { __ } from '@/translation'

const CSRF_RELOAD_FLAG = 'pranera:csrf-reloaded'

export function currentPath() {
  return window.location.pathname + window.location.search + window.location.hash
}

export function loginUrl(path = currentPath()) {
  return `/login?redirect-to=${encodeURIComponent(path)}`
}

export function redirectToLogin() {
  window.location.assign(loginUrl())
}

/** /deal_wizard/<lead> -> the same lead in CRM; anything else -> the CRM home. */
export function crmUrlForPath(pathname = window.location.pathname) {
  const [, lead] = pathname.replace(/^\/deal_wizard\/?/, '/').split('/')
  return lead ? `/crm/leads/${encodeURIComponent(decodeURIComponent(lead))}` : '/crm'
}

const navigating = () => new Promise(() => {})

/**
 * Who does the server think we are? `null` means "couldn't tell" (offline /
 * network error), which must never be mistaken for an expired session.
 */
async function loggedUser() {
  try {
    const res = await fetch('/api/method/pranera_crm.api.whoami', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (res.status === 401) return 'Guest'
    if (!res.ok) return null
    return (await res.json()).message || 'Guest'
  } catch {
    return null
  }
}

export function isAuthFailure(err) {
  return (
    err?.status === 401 ||
    err?.status === 403 ||
    ['CSRFTokenError', 'AuthenticationError', 'SessionExpired'].includes(err?.exc_type)
  )
}

/**
 * `call()` plus session handling:
 *  - expired session  -> /login?redirect-to=<current path> (never a raw CSRF error)
 *  - stale CSRF token on a live session -> reload once to fetch a fresh token
 * Everything else is rethrown for the caller to display.
 */
export async function api(method, params = {}) {
  try {
    const result = await call(method, params)
    sessionStorage.removeItem(CSRF_RELOAD_FLAG)
    return result
  } catch (err) {
    if (err?.exc_type === 'WizardDisabled') {
      window.location.assign(crmUrlForPath())
      return navigating()
    }
    if (isAuthFailure(err)) {
      const user = await loggedUser()
      if (user === 'Guest') {
        redirectToLogin()
        return navigating()
      }
      if (user && err.exc_type === 'CSRFTokenError' && !sessionStorage.getItem(CSRF_RELOAD_FLAG)) {
        sessionStorage.setItem(CSRF_RELOAD_FLAG, '1')
        window.location.reload()
        return navigating()
      }
    }
    throw err
  }
}

const TAGS = /<[^>]*>/g

export function stripHtml(text) {
  return String(text ?? '')
    .replace(TAGS, '')
    .replace(/&nbsp;/g, ' ')
    .trim()
}

/** Human readable message from a frappe-ui `call` error. */
export function errorMessage(err) {
  if (err instanceof TypeError || err?.status === undefined) {
    if (!navigator.onLine || err instanceof TypeError) {
      return __('Could not reach the server. Check your connection; your draft is saved on this device.')
    }
  }
  if (err?.exc_type === 'MandatoryError') {
    const message = (err.messages || [])
      .map((m) => stripHtml(m).split(': ').pop().trim())
      .filter(Boolean)
      .join(', ')
    if (!message) return __('Some required fields are missing.')
    return /required/i.test(message) ? message : __('{0} is required', [message])
  }
  const first = (err?.messages || []).map(stripHtml).find(Boolean)
  return first || __('Something went wrong. Please try again.')
}
