// Site properties, as CRM follows them: language, direction, formats, currency
// and branding. They arrive in the boot data as `window.pranera_site`
// (see pranera_crm/settings.py).

const DEFAULTS = {
  lang: 'en',
  rtl: false,
  timezone: { system: null, user: null },
  date_format: 'yyyy-mm-dd',
  time_format: 'HH:mm:ss',
  number_format: '#,###.##',
  float_precision: 3,
  currency_precision: 2,
  currency: null,
  currency_symbol: null,
  brand: { name: null, logo: null, favicon: null },
}

export function getSite() {
  const site = (typeof window !== 'undefined' && window.pranera_site) || {}
  return { ...DEFAULTS, ...site, brand: { ...DEFAULTS.brand, ...(site.brand || {}) } }
}

/** Language / direction on <html>, tab title and favicon from the CRM branding settings. */
export function applySiteProperties(defaults = { title: 'Pranera CRM' }) {
  const site = getSite()
  const root = document.documentElement
  root.lang = site.lang
  root.dir = site.rtl ? 'rtl' : 'ltr'

  document.title = site.brand.name || defaults.title

  if (site.brand.favicon) {
    let link = document.querySelector('link[rel="icon"]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.removeAttribute('type')
    link.removeAttribute('sizes')
    link.href = site.brand.favicon
  }
}
