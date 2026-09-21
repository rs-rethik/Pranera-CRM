import { describe, expect, it } from 'vitest'
import { applyDraft, createForm, toPayload } from '@/lib/form'
import { flattenLayout, isClientRequired, selectOptions } from '@/lib/layout'
import { STEPS, firstInvalidStep, resolveStep, validateStep } from '@/lib/validation'

const dealLayout = [
  {
    name: 'first_tab',
    sections: [
      {
        columns: [
          {
            fields: [
              { fieldname: 'status', label: 'Status', fieldtype: 'Link', options: 'CRM Deal Status', reqd: 1 },
              { fieldname: 'expected_value', label: 'Value', fieldtype: 'Currency' },
              { fieldname: 'notes', label: 'Notes', fieldtype: 'Small Text', reqd: 1, depends_on: 'eval:doc.x' },
              { fieldname: 'proof', label: 'Proof', fieldtype: 'Attach', reqd: 1 },
              { fieldname: 'active', label: 'Active', fieldtype: 'Check', reqd: 1 },
            ],
          },
        ],
      },
    ],
  },
]

const ctx = {
  lead: { name: 'CRM-LEAD-1', organization: 'Acme', first_name: 'Ada', email: 'ada@acme.test' },
  organization_fields: [{ fieldname: 'organization' }, { fieldname: 'website' }],
  contact_fields: [{ fieldname: 'first_name' }, { fieldname: 'email' }],
  candidates: { auto_organization: null, auto_contact: null },
  deal_layout: dealLayout,
  deal_defaults: {},
}

describe('layout helpers', () => {
  it('flattens tabs/sections/columns in order', () => {
    expect(flattenLayout(dealLayout).map((f) => f.fieldname)).toEqual([
      'status',
      'expected_value',
      'notes',
      'proof',
      'active',
    ])
  })

  it('only insists on values it can actually check', () => {
    const byName = Object.fromEntries(flattenLayout(dealLayout).map((f) => [f.fieldname, f]))
    expect(isClientRequired(byName.status)).toBe(true)
    expect(isClientRequired(byName.notes)).toBe(false) // conditional: server decides
    expect(isClientRequired(byName.proof)).toBe(false) // can't be rendered here
    expect(isClientRequired(byName.active)).toBe(false) // a Check is always "filled"
  })

  it('adds an empty row to optional selects only', () => {
    expect(selectOptions({ options: 'A\nB' })).toEqual(['', 'A', 'B'])
    expect(selectOptions({ options: 'A\nB', reqd: 1 })).toEqual(['A', 'B'])
  })
})

describe('form state', () => {
  it('starts from the lead and prefers an exact existing match', () => {
    const form = createForm({
      ...ctx,
      lead: { organization: 'Acme', website: 'https://acme.test', first_name: 'Ada', email: 'a@b.co' },
      candidates: { auto_organization: 'Acme', auto_contact: null },
    })
    expect(form.organization).toMatchObject({ mode: 'existing', existing: 'Acme' })
    expect(form.organization.values.website).toBe('https://acme.test')
    expect(form.contact.mode).toBe('new')
    expect(form.contact.values.first_name).toBe('Ada')
  })

  it('restores only known fields from a draft', () => {
    const form = createForm(ctx)
    applyDraft(form, {
      form: {
        organization: { mode: 'existing', existing: 'Globex', values: { organization: 'Edited', bogus: 1 } },
        contact: { mode: 'weird', values: {} },
        deal: { status: 'Won' },
      },
    })
    expect(form.organization.mode).toBe('existing')
    expect(form.organization.existing).toBe('Globex')
    expect(form.organization.values.organization).toBe('Edited')
    expect('bogus' in form.organization.values).toBe(false)
    expect(form.contact.mode).toBe('new') // invalid mode ignored
    expect(form.deal.status).toBe('Won')
  })

  it('builds the convert payload: edits only for "new", ids only for "existing"', () => {
    const form = createForm(ctx)
    form.organization.values.organization = '  Acme Ltd '
    form.deal.status = 'Qualification'
    form.deal.expected_value = ''

    const payload = toPayload(form, 'CRM-LEAD-1')
    expect(payload.existing_organization).toBe('')
    expect(payload.lead_updates.organization).toBe('Acme Ltd')
    expect(payload.lead_updates.first_name).toBe('Ada')
    expect(payload.deal).toEqual({ status: 'Qualification' }) // empty values dropped

    form.organization.mode = 'existing'
    form.organization.existing = 'Globex'
    const second = toPayload(form, 'CRM-LEAD-1')
    expect(second.existing_organization).toBe('Globex')
    expect('organization' in second.lead_updates).toBe(false)
  })
})

describe('per-step validation and the step guard', () => {
  it('requires a choice when using an existing record', () => {
    const form = createForm(ctx)
    form.organization.mode = 'existing'
    expect(validateStep(0, form, ctx)).toHaveProperty('existing')
    form.organization.existing = 'Acme'
    expect(validateStep(0, form, ctx)).toEqual({})
  })

  it('requires a first name and a valid email for a new contact', () => {
    const form = createForm(ctx)
    form.contact.values.first_name = ' '
    form.contact.values.email = 'nope'
    expect(Object.keys(validateStep(1, form, ctx)).sort()).toEqual(['email', 'first_name'])
  })

  it('requires the deal fields from the layout', () => {
    const form = createForm(ctx)
    expect(validateStep(2, form, ctx)).toHaveProperty('status')
    form.deal.status = 'Won'
    expect(validateStep(2, form, ctx)).toEqual({})
  })

  it('never lets ?step= run ahead of the first invalid step', () => {
    const form = createForm(ctx)
    expect(firstInvalidStep(form, ctx)).toBe(2) // deal status missing
    expect(resolveStep('4', form, ctx)).toBe(2)
    expect(resolveStep('1', form, ctx)).toBe(0)
    expect(resolveStep('garbage', form, ctx)).toBe(0)
    expect(resolveStep('99', form, ctx)).toBe(2)

    form.deal.status = 'Won'
    expect(resolveStep('4', form, ctx)).toBe(STEPS.length - 1)
    expect(resolveStep('0', form, ctx)).toBe(0)
  })
})
