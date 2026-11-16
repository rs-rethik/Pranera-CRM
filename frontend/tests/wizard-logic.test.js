import { describe, expect, it } from 'vitest'
import { applyDraft, createForm, customerPayload, toPayload } from '@/lib/form'
import { flattenLayout, isClientRequired, selectOptions } from '@/lib/layout'
import {
	STEPS,
	firstInvalidStep,
	isSkipped,
	needsAddress,
	resolveStep,
	stepAfter,
	stepBefore,
	validateStep,
} from '@/lib/validation'

const dealLayout = [
	{
		name: 'first_tab',
		sections: [
			{
				columns: [
					{
						fields: [
							{
								fieldname: 'status',
								label: 'Status',
								fieldtype: 'Link',
								options: 'CRM Deal Status',
								reqd: 1,
							},
							{ fieldname: 'expected_value', label: 'Value', fieldtype: 'Currency' },
							{
								fieldname: 'notes',
								label: 'Notes',
								fieldtype: 'Small Text',
								reqd: 1,
								depends_on: 'eval:doc.x',
							},
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
		expect(isClientRequired(byName.notes)).toBe(false)
		expect(isClientRequired(byName.proof)).toBe(false)
		expect(isClientRequired(byName.active)).toBe(false)
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
			lead: {
				organization: 'Acme',
				website: 'https://acme.test',
				first_name: 'Ada',
				email: 'a@b.co',
			},
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
				organization: {
					mode: 'existing',
					existing: 'Globex',
					values: { organization: 'Edited', bogus: 1 },
				},
				contact: { mode: 'weird', values: {} },
				deal: { status: 'Won' },
			},
		})
		expect(form.organization.mode).toBe('existing')
		expect(form.organization.existing).toBe('Globex')
		expect(form.organization.values.organization).toBe('Edited')
		expect('bogus' in form.organization.values).toBe(false)
		expect(form.contact.mode).toBe('new')
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
		expect(payload.deal).toEqual({ status: 'Qualification' })

		form.organization.mode = 'existing'
		form.organization.existing = 'Globex'
		const second = toPayload(form, 'CRM-LEAD-1')
		expect(second.existing_organization).toBe('Globex')
		expect('organization' in second.lead_updates).toBe(false)
	})

	it('always sets up the ERPNext customer when the bridge is on, even if a draft says otherwise', () => {
		const ctxWithCustomer = {
			...ctx,
			customer: {
				enabled: true,
				organization_questions: [],
				contact_questions: [],
				address_fields: [],
			},
		}
		const form = createForm(ctxWithCustomer)
		applyDraft(form, { form: { customer: { enabled: false } } })
		expect(form.customer.enabled).toBe(true)
		expect(customerPayload(form).setup_customer).toBe(true)
	})

	it('sends address values for "new" and customer_existing_address for "existing"', () => {
		const ctxWithCustomer = {
			...ctx,
			customer: {
				enabled: true,
				organization_questions: [],
				contact_questions: [],
				address_fields: [{ fieldname: 'address_line1' }, { fieldname: 'city' }],
			},
		}
		const form = createForm(ctxWithCustomer)
		form.customer.address.values.address_line1 = '1 MG Road'
		let payload = customerPayload(form)
		expect(payload.customer_address).toEqual({ address_line1: '1 MG Road' })
		expect(payload.customer_existing_address).toBe('')

		form.customer.address.mode = 'existing'
		form.customer.address.existing = 'Some Address-Billing'
		payload = customerPayload(form)
		expect(payload.customer_address).toEqual({})
		expect(payload.customer_existing_address).toBe('Some Address-Billing')
	})
})

describe('per-step validation and the step guard', () => {
	it('requires a choice when using an existing record', () => {
		const form = createForm(ctx)
		form.organization.mode = 'existing'
		expect(validateStep(1, form, ctx)).toHaveProperty('existing')
		form.organization.existing = 'Acme'
		expect(validateStep(1, form, ctx)).toEqual({})
	})

	it('requires a first name and a valid email for a new contact', () => {
		const form = createForm(ctx)
		form.contact.values.first_name = ' '
		form.contact.values.email = 'nope'
		expect(Object.keys(validateStep(2, form, ctx)).sort()).toEqual(['email', 'first_name'])
	})

	it('requires the deal fields from the layout', () => {
		const form = createForm(ctx)
		expect(validateStep(3, form, ctx)).toHaveProperty('status')
		form.deal.status = 'Won'
		expect(validateStep(3, form, ctx)).toEqual({})
	})

	it('requires State once an Indian address is started', () => {
		const ctxWithCustomer = {
			...ctx,
			customer: {
				enabled: true,
				organization_questions: [],
				contact_questions: [],
				address_fields: [
					{ fieldname: 'address_line1' },
					{ fieldname: 'city' },
					{ fieldname: 'country' },
					{ fieldname: 'state' },
				],
			},
		}
		const form = createForm(ctxWithCustomer)
		form.customer.address.values.address_line1 = '1 MG Road'
		form.customer.address.values.city = 'Chennai'
		form.customer.address.values.country = 'India'
		expect(validateStep(1, form, ctxWithCustomer)).toHaveProperty('customer_state')
		form.customer.address.values.state = 'Tamil Nadu'
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})

		form.customer.address.values.country = 'United States'
		form.customer.address.values.state = ''
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})
	})

	it('requires a GSTIN once "Does the customer have a GST Number?" is Yes', () => {
		const ctxWithCustomer = {
			...ctx,
			customer: {
				enabled: true,
				organization_questions: [],
				contact_questions: [],
				address_fields: [],
			},
		}
		const form = createForm(ctxWithCustomer)
		form.customer.answers.gst_registered = 'yes'
		expect(validateStep(1, form, ctxWithCustomer)).toHaveProperty('customer_gstin')
		form.customer.address.values.gstin = '27AAPFU0939F1ZV'
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})

		form.customer.address.values.gstin = ''
		form.customer.answers.gst_registered = 'no'
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})

		form.customer.answers.gst_registered = 'yes'
		form.customer.address.mode = 'existing'
		form.customer.address.existing = 'Some Address-Billing'
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})
	})

	it('requires picking one once "Choose Existing" is on for the address', () => {
		const ctxWithCustomer = {
			...ctx,
			customer: {
				enabled: true,
				organization_questions: [],
				contact_questions: [],
				address_fields: [],
			},
		}
		const form = createForm(ctxWithCustomer)
		form.customer.address.mode = 'existing'
		expect(validateStep(1, form, ctxWithCustomer)).toHaveProperty('customer_existing_address')
		form.customer.address.existing = 'Some Address-Billing'
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})
	})

	it('never lets ?step= run ahead of the first invalid step', () => {
		const form = createForm(ctx)
		form.contact.emailVerification.verifiedEmail = form.contact.values.email
		expect(firstInvalidStep(form, ctx)).toBe(0) // the GSTIN step comes first
		form.gstin.none = true
		expect(firstInvalidStep(form, ctx)).toBe(3)
		expect(resolveStep('5', form, ctx)).toBe(3)
		expect(resolveStep('2', form, ctx)).toBe(1)
		expect(resolveStep('garbage', form, ctx)).toBe(0)
		expect(resolveStep('99', form, ctx)).toBe(3)

		form.deal.status = 'Won'
		expect(resolveStep('5', form, ctx)).toBe(STEPS.length - 1)
		expect(resolveStep('0', form, ctx)).toBe(0)
	})
})

describe('the GSTIN step', () => {
	const existing = [
		{ customer: 'ACME-1', customer_name: 'ACME' },
		{ customer: 'ACME-2', customer_name: 'ACME' },
	]

	it('needs "No GSTIN" or a checked, valid GSTIN', () => {
		const form = createForm(ctx)
		expect(validateStep(0, form, ctx)).toHaveProperty('gstin')
		form.gstin.value = 'not a gstin'
		expect(validateStep(0, form, ctx)).toHaveProperty('gstin')
		form.gstin.value = '33abcde1234f1z5'
		expect(validateStep(0, form, ctx).gstin).toMatch(/Check/)
		form.gstin.checked = '33ABCDE1234F1Z5'
		expect(validateStep(0, form, ctx)).toEqual({})
		form.gstin.value = ''
		form.gstin.none = true
		expect(validateStep(0, form, ctx)).toEqual({})
	})

	it('needs a choice when several customers have the GSTIN', () => {
		const form = createForm(ctx)
		form.gstin.value = form.gstin.checked = '33ABCDE1234F1Z5'
		form.gstin.existing = existing
		expect(validateStep(0, form, ctx)).toHaveProperty('gstin_customer')
		form.gstin.customer = 'ACME-2'
		expect(validateStep(0, form, ctx)).toEqual({})
	})

	it('skips the Organization step for an existing customer, and Contact when the contact exists', () => {
		const form = createForm(ctx)
		form.gstin.value = form.gstin.checked = '33ABCDE1234F1Z5'
		form.gstin.existing = existing
		form.gstin.customer = 'ACME-1'
		expect(isSkipped(1, form)).toBe(true)
		expect(isSkipped(2, form)).toBe(false) // a new contact still needs its step
		expect(stepAfter(0, form)).toBe(2)
		form.contact.mode = 'existing'
		form.contact.existing = 'Ada Lovelace'
		expect(isSkipped(2, form)).toBe(true)
		expect(stepAfter(0, form)).toBe(3)
		expect(stepBefore(3, form)).toBe(0)
	})

	it('with no GSTIN, needs a choice between the matching customers and a new one', () => {
		const form = createForm(ctx)
		form.gstin.none = true
		expect(validateStep(0, form, ctx)).toEqual({})
		form.gstin.existing = existing
		expect(validateStep(0, form, ctx)).toHaveProperty('gstin_customer')
		form.gstin.newCustomer = true
		expect(validateStep(0, form, ctx)).toEqual({})
	})

	it('with no GSTIN, a new customer needs its address', () => {
		const ctxWithCustomer = {
			...ctx,
			customer: {
				enabled: true,
				organization_questions: [],
				contact_questions: [],
				address_fields: [
					'address_line1',
					'city',
					'state',
					'pincode',
					'country',
					'gstin',
				].map((fieldname) => ({ fieldname, label: fieldname, fieldtype: 'Data' })),
			},
		}
		const form = createForm(ctxWithCustomer)
		form.gstin.none = true
		form.gstin.newCustomer = true
		expect(needsAddress(form)).toBe(true)
		const errors = validateStep(1, form, ctxWithCustomer)
		for (const key of [
			'customer_address_line1',
			'customer_city',
			'customer_pincode',
			'customer_country',
		])
			expect(errors).toHaveProperty(key)
		Object.assign(form.customer.address.values, {
			address_line1: '1 Mill Road',
			city: 'Tiruppur',
			pincode: '641603',
			country: 'India',
		})
		expect(validateStep(1, form, ctxWithCustomer)).toHaveProperty('customer_state')
		form.customer.address.values.state = 'Tamil Nadu'
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})
		// an existing address is fine too
		form.customer.address.values.address_line1 = ''
		form.customer.address.mode = 'existing'
		form.customer.address.existing = 'Mill-Billing'
		expect(validateStep(1, form, ctxWithCustomer)).toEqual({})
		// with a GSTIN, or for an existing customer, the address stays optional
		form.gstin.customer = 'ACME-1'
		expect(needsAddress(form)).toBe(false)
	})

	it('links an existing customer instead of setting one up', () => {
		const form = createForm({ ...ctx, customer: { enabled: true } })
		form.organization.values.organization = 'Typed Name'
		form.gstin.existing = existing
		form.gstin.customer = 'ACME-1'
		const payload = toPayload(form, 'CRM-LEAD-1')
		expect(payload.existing_customer).toBe('ACME-1')
		expect(payload.setup_customer).toBe(false)
		expect(payload.existing_organization).toBe('')
		expect(payload.lead_updates).toEqual({})
	})
})
