import { reactive } from 'vue'
import { isEmpty } from './layout'

/** Build the wizard's single reactive form state from the server context. */
export function createForm(ctx) {
  const lead = ctx.lead
  const pick = (fields) =>
    Object.fromEntries(fields.map((f) => [f.fieldname, lead[f.fieldname] ?? '']))

  const { auto_organization, auto_contact } = ctx.candidates || {}

  return reactive({
    organization: {
      // an exact name match is what CRM would reuse anyway, so start there
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
}

const blank = (v) => (typeof v === 'string' ? v.trim() : v)

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
  }
}
