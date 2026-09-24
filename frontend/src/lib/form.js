import { reactive } from 'vue'
import { isEmpty } from './layout'

/** Build the wizard's single reactive form state from the server context. */
export function createForm(ctx) {
  const lead = ctx.lead
  const pick = (fields) =>
    Object.fromEntries(fields.map((f) => [f.fieldname, lead[f.fieldname] ?? '']))

  const { auto_organization, auto_contact } = ctx.candidates || {}

  const addressFields = Object.fromEntries((ctx.customer?.address_fields || []).map((f) => [f.fieldname, '']))

  return reactive({
    organization: {
      mode: auto_organization ? 'existing' : 'new',
      existing: auto_organization || '',
      values: pick(ctx.organization_fields),
    },
    contact: {
      mode: auto_contact ? 'existing' : 'new',
      existing: auto_contact || '',
      values: pick(ctx.contact_fields),
    },
    deal: { ...(ctx.deal_defaults || {}) },
    customer: {
      enabled: !!ctx.customer?.enabled,
      answers: {},
      contactAnswers: {},
      overrides: {},
      address: {
        mode: 'new',
        existing: '',
        values: addressFields,
      },
    },
  })
}

/** Copy a saved draft over a fresh form, ignoring anything unexpected. */
export function applyDraft(form, draft) {
  const saved = draft?.form
  if (!saved) return
  for (const key of ['organization', 'contact']) {
    if (!saved[key]) continue
    if (['new', 'existing'].includes(saved[key].mode)) form[key].mode = saved[key].mode
    if (typeof saved[key].existing === 'string') form[key].existing = saved[key].existing
    for (const field of Object.keys(form[key].values)) {
      if (field in (saved[key].values || {})) form[key].values[field] = saved[key].values[field]
    }
  }
  if (saved.deal && typeof saved.deal === 'object') Object.assign(form.deal, saved.deal)

  if (saved.customer && typeof saved.customer === 'object') {
    if (typeof saved.customer.enabled === 'boolean') form.customer.enabled = saved.customer.enabled
    for (const key of ['answers', 'contactAnswers', 'overrides']) {
      if (saved.customer[key] && typeof saved.customer[key] === 'object') {
        Object.assign(form.customer[key], saved.customer[key])
      }
    }
    const savedAddress = saved.customer.address
    if (savedAddress && typeof savedAddress === 'object') {
      if (['new', 'existing'].includes(savedAddress.mode)) form.customer.address.mode = savedAddress.mode
      if (typeof savedAddress.existing === 'string') form.customer.address.existing = savedAddress.existing
      for (const field of Object.keys(form.customer.address.values)) {
        if (field in (savedAddress.values || {})) form.customer.address.values[field] = savedAddress.values[field]
      }
    }
  }
}

const blank = (v) => (typeof v === 'string' ? v.trim() : v)

function cleaned(obj) {
  const out = {}
  for (const [key, value] of Object.entries(obj || {})) {
    if (!isEmpty(value)) out[key] = blank(value)
  }
  return out
}

/** Arguments for pranera_crm.api.convert. */
export function toPayload(form, lead) {
  const leadUpdates = {}
  if (form.organization.mode === 'new') Object.assign(leadUpdates, form.organization.values)
  if (form.contact.mode === 'new') Object.assign(leadUpdates, form.contact.values)
  for (const key of Object.keys(leadUpdates)) leadUpdates[key] = blank(leadUpdates[key])

  const deal = {}
  for (const [key, value] of Object.entries(form.deal)) {
    if (!isEmpty(value)) deal[key] = blank(value)
  }

  return {
    lead,
    deal,
    existing_organization: form.organization.mode === 'existing' ? form.organization.existing : '',
    existing_contact: form.contact.mode === 'existing' ? form.contact.existing : '',
    lead_updates: leadUpdates,
    ...customerPayload(form),
  }
}

/** The `convert()` / `setup_customer_for_deal()` args for the ERPNext Customer section. */
export function customerPayload(form) {
  const customer = form.customer
  const address = customer?.address
  return {
    setup_customer: !!customer?.enabled,
    customer_answers: cleaned(customer?.answers),
    contact_customer_answers: cleaned(customer?.contactAnswers),
    customer_address: address?.mode === 'existing' ? {} : cleaned(address?.values),
    customer_existing_address: address?.mode === 'existing' ? address.existing : '',
    customer_overrides: cleaned(customer?.overrides),
  }
}
