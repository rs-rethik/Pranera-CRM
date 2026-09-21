import { __ } from '@/translation'
import { flattenLayout, isClientRequired, isEmpty } from './layout'

export const STEPS = [
  { key: 'organization', label: 'Organization' },
  { key: 'contact', label: 'Contact' },
  { key: 'deal', label: 'Deal details' },
  { key: 'review', label: 'Review' },
]

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/**
 * Validate one step. Returns { fieldname: message }; an empty object means the
 * step is valid. `form` is the wizard's single reactive state, `ctx` the
 * context returned by the server.
 */
export function validateStep(index, form, ctx) {
  const errors = {}

  if (index === 0) {
    const org = form.organization
    if (org.mode === 'existing') {
      if (!org.existing) errors.existing = __('Please select an existing organization')
    } else if (!isEmpty(org.values.annual_revenue) && Number(org.values.annual_revenue) < 0) {
      errors.annual_revenue = __('Annual revenue cannot be negative')
    }
  }

  if (index === 1) {
    const contact = form.contact
    if (contact.mode === 'existing') {
      if (!contact.existing) errors.existing = __('Please select an existing contact')
    } else {
      if (isEmpty(contact.values.first_name?.trim?.() ?? contact.values.first_name)) {
        errors.first_name = __('{0} is required', [__('First Name')])
      }
      const email = contact.values.email
      if (!isEmpty(email) && !EMAIL.test(String(email).trim())) errors.email = __('Enter a valid email address')
    }
  }

  if (index === 2) {
    for (const field of flattenLayout(ctx?.deal_layout)) {
      if (isClientRequired(field) && isEmpty(form.deal[field.fieldname])) {
        errors[field.fieldname] = __('{0} is required', [__(field.label || field.fieldname)])
      }
    }
  }

  return errors
}

export const isStepValid = (index, form, ctx) => Object.keys(validateStep(index, form, ctx)).length === 0

/** Index of the first step that is not yet valid, or the Review step if none. */
export function firstInvalidStep(form, ctx) {
  for (let i = 0; i < STEPS.length - 1; i++) {
    if (!isStepValid(i, form, ctx)) return i
  }
  return STEPS.length - 1
}

/** Parse a `?step=` value (1-based) into a valid 0-based index, never past the first invalid step. */
export function resolveStep(queryStep, form, ctx) {
  const requested = Number.parseInt(queryStep, 10)
  const wanted = Number.isFinite(requested) ? Math.min(Math.max(requested, 1), STEPS.length) - 1 : 0
  return Math.min(wanted, firstInvalidStep(form, ctx))
}
