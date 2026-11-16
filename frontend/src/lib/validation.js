import { __ } from '@/translation'
import { flattenLayout, isClientRequired, isEmpty } from './layout'
import { unansweredMandatory } from './questions'

export const STEPS = [
	{ key: 'gstin', label: 'GSTIN' },
	{ key: 'organization', label: 'Organization' },
	{ key: 'contact', label: 'Contact' },
	{ key: 'deal', label: 'Deal details' },
	{ key: 'review', label: 'Review' },
]

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export const normalizeEmail = (email) =>
	String(email ?? '')
		.trim()
		.toLowerCase()
export const isValidEmail = (email) => EMAIL.test(String(email).trim())

const GST_GATE_KEY = 'gst_registered'
export const GSTIN_FORMAT = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/

const ADDRESS_LABELS = {
	address_line1: 'Address Line 1',
	city: 'City',
	pincode: 'Postal Code',
	country: 'Country',
}

/** No GSTIN and a new customer: nothing fills the customer's address, so the Organization step asks
 * for it. */
export const needsAddress = (form) => !!form?.gstin?.none && !form.gstin.customer

/** With an existing customer chosen on the GSTIN step, its organization is used as it is: the
 * Organization step is skipped, and so is the Contact step when the lead's contact already exists
 * (a new contact still needs its details and email check there). */
export function isSkipped(index, form) {
	const key = STEPS[index]?.key
	if (!form?.gstin?.customer) return false
	return key === 'organization' || (key === 'contact' && form.contact?.mode === 'existing')
}

/** Bridge-independent questions (Territory, Industry, ...) always apply; the rest
 * only when the "Set up this customer in ERPNext" toggle is on for this conversion. */
function bridgeAwareQuestions(questions, bridgeToggleOn) {
	return (questions || []).filter((q) => bridgeToggleOn || !q.requires_erpnext_bridge)
}

/**
 * Validate one step. Returns { fieldname: message }; an empty object means the
 * step is valid. `form` is the wizard's single reactive state, `ctx` the
 * context returned by the server.
 */
export function validateStep(index, form, ctx) {
	const errors = {}
	const key = STEPS[index]?.key
	if (isSkipped(index, form)) return errors

	if (key === 'gstin') {
		const g = form.gstin
		if (g.none) {
			if (g.existing.length && !g.customer && !g.newCustomer) {
				errors.gstin_customer = __('Choose the existing customer, or "New customer"')
			}
		} else {
			const value = (g.value || '').trim().toUpperCase()
			if (!GSTIN_FORMAT.test(value)) {
				errors.gstin = __('Enter a valid 15-character GSTIN, or choose "No GSTIN"')
			} else if (g.checked !== value) {
				errors.gstin = __('Check the GSTIN to continue')
			} else if (g.existing.length && !g.customer) {
				errors.gstin_customer = __('Choose the customer this deal is for')
			}
		}
	}

	if (key === 'organization') {
		const org = form.organization
		if (org.mode === 'existing') {
			if (!org.existing) errors.existing = __('Please select an existing organization')
		} else if (!isEmpty(org.values.annual_revenue) && Number(org.values.annual_revenue) < 0) {
			errors.annual_revenue = __('Annual revenue cannot be negative')
		}

		const address = form.customer?.address
		if (form.customer?.enabled && address?.mode === 'existing') {
			if (!address.existing)
				errors.customer_existing_address = __('Please select an existing address')
		} else if (form.customer?.enabled && address && !isEmpty(address.values.address_line1)) {
			if (isEmpty(address.values.city))
				errors.customer_city = __('{0} is required', [__('City')])
			if (isEmpty(address.values.country))
				errors.customer_country = __('{0} is required', [__('Country')])
			if (address.values.country === 'India' && isEmpty(address.values.state)) {
				errors.customer_state = __('{0} is required', [__('State')])
			}
		}

		// no GSTIN and a new customer: its address is entered here, so it is required
		if (form.customer?.enabled && needsAddress(form) && address?.mode !== 'existing') {
			for (const field of ['address_line1', 'city', 'pincode', 'country']) {
				if (isEmpty(address?.values[field]))
					errors[`customer_${field}`] = __('{0} is required', [
						__(ADDRESS_LABELS[field]),
					])
			}
			if (address?.values.country === 'India' && isEmpty(address?.values.state))
				errors.customer_state = __('{0} is required', [__('State')])
		}

		if (
			form.customer?.enabled &&
			address?.mode !== 'existing' &&
			form.customer.answers?.[GST_GATE_KEY] === 'yes' &&
			isEmpty(address?.values.gstin)
		) {
			errors.customer_gstin = __('{0} is required', [__('GSTIN / UIN')])
		}

		const orgQuestions = bridgeAwareQuestions(
			ctx?.customer?.organization_questions,
			form.customer?.enabled
		)
		for (const q of unansweredMandatory(orgQuestions, form.customer?.answers)) {
			errors[`cq_${q.question_key}`] = __('{0} is required', [q.label])
		}
	}

	if (key === 'contact') {
		const contact = form.contact
		if (contact.mode === 'existing') {
			if (!contact.existing) errors.existing = __('Please select an existing contact')
		} else {
			if (isEmpty(contact.values.first_name?.trim?.() ?? contact.values.first_name)) {
				errors.first_name = __('{0} is required', [__('First Name')])
			}
			const email = contact.values.email
			if (!isEmpty(email) && !isValidEmail(email))
				errors.email = __('Enter a valid email address')
			else if (
				!isEmpty(email) &&
				normalizeEmail(email) !== normalizeEmail(contact.emailVerification?.verifiedEmail)
			) {
				errors.email = __('Verify this email address before continuing')
			}
		}
		const contactQuestions = bridgeAwareQuestions(
			ctx?.customer?.contact_questions,
			form.customer?.enabled
		)
		for (const q of unansweredMandatory(contactQuestions, form.customer?.contactAnswers)) {
			errors[`cq_${q.question_key}`] = __('{0} is required', [q.label])
		}
	}

	if (key === 'deal') {
		for (const field of flattenLayout(ctx?.deal_layout)) {
			if (isClientRequired(field) && isEmpty(form.deal[field.fieldname])) {
				errors[field.fieldname] = __('{0} is required', [
					__(field.label || field.fieldname),
				])
			}
		}
	}

	return errors
}

export const isStepValid = (index, form, ctx) =>
	Object.keys(validateStep(index, form, ctx)).length === 0

/** Index of the first step that is not yet valid, or the Review step if none. */
export function firstInvalidStep(form, ctx) {
	for (let i = 0; i < STEPS.length - 1; i++) {
		if (!isStepValid(i, form, ctx)) return i
	}
	return STEPS.length - 1
}

/** Parse a `?step=` value (1-based) into a valid 0-based index, never past the first invalid step
 * and never a skipped one. */
export function resolveStep(queryStep, form, ctx) {
	const requested = Number.parseInt(queryStep, 10)
	const wanted = Number.isFinite(requested)
		? Math.min(Math.max(requested, 1), STEPS.length) - 1
		: 0
	return stepAfter(Math.min(wanted, firstInvalidStep(form, ctx)) - 1, form)
}

/** The next step after `index` that is not skipped. */
export function stepAfter(index, form) {
	let i = index + 1
	while (i < STEPS.length - 1 && isSkipped(i, form)) i++
	return i
}

/** The step before `index` that is not skipped. */
export function stepBefore(index, form) {
	let i = index - 1
	while (i > 0 && isSkipped(i, form)) i--
	return Math.max(i, 0)
}
