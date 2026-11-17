<template>
	<div class="space-y-4">
		<h2 class="text-center text-xl font-semibold text-ink-gray-9">{{ __('GSTIN') }}</h2>
		<p class="text-center text-base text-ink-gray-6">
			{{
				__(
					"Enter the customer's GSTIN. An existing customer is used as it is; for a new one the name and address come from the GST portal."
				)
			}}
		</p>

		<Switch v-model="g.none" :label="__('No GSTIN (unregistered or individual)')" />

		<!-- no GSTIN: customers the lead may already be (by its mobile or company name) -->
		<template v-if="g.none">
			<p v-if="loadingMatches" class="text-sm text-ink-gray-5">
				{{ __('Looking for existing customers...') }}
			</p>
			<ErrorMessage :message="checkError" />
			<template v-if="!loadingMatches && g.existing.length">
				<p class="text-base text-ink-gray-7">
					{{
						__(
							"These customers match the lead's mobile number or company name. Choose one, or create a new customer:"
						)
					}}
				</p>
				<label
					v-for="c in g.existing"
					:key="c.customer"
					class="flex cursor-pointer gap-3 rounded border p-3"
					:class="choiceClass(c.customer)"
				>
					<input v-model="choice" type="radio" class="mt-1" :value="c.customer" />
					<span class="min-w-0">
						<span class="font-medium text-ink-gray-9">{{ c.customer_name }}</span>
						<span v-if="c.customer !== c.customer_name" class="text-ink-gray-5">
							({{ c.customer }})</span
						>
						<span class="text-ink-gray-5">
							·
							{{
								c.matched_by === 'mobile'
									? __('same mobile number')
									: __('same company name')
							}}</span
						>
						<span v-if="c.disabled" class="text-ink-amber-3">
							· {{ __('Disabled') }}</span
						>
						<span class="mt-1 block text-sm text-ink-gray-6">{{
							summaryLine(c)
						}}</span>
					</span>
				</label>
				<label
					class="flex cursor-pointer gap-3 rounded border p-3"
					:class="choiceClass(NEW)"
				>
					<input v-model="choice" type="radio" class="mt-1" :value="NEW" />
					<span>
						<span class="font-medium text-ink-gray-9">{{ __('New customer') }}</span>
						<span class="mt-1 block text-sm text-ink-gray-6">{{
							__('Enter its details and address on the next step.')
						}}</span>
					</span>
				</label>
				<ErrorMessage
					v-if="showErrors && errors.gstin_customer"
					:message="errors.gstin_customer"
				/>
			</template>
			<p v-else-if="!loadingMatches && !checkError" class="text-sm text-ink-gray-5">
				{{
					__(
						"No existing customer has this lead's mobile number or company name. A new customer is created: enter its details and address on the next step."
					)
				}}
			</p>
		</template>

		<template v-if="!g.none">
			<div class="flex items-end gap-2">
				<FormControl
					v-model="g.value"
					type="text"
					class="flex-1"
					:label="__('GSTIN / UIN')"
					placeholder="33ABCDE1234F1Z5"
					maxlength="15"
					:aria-invalid="showErrors && !!errors.gstin"
					@keydown.enter.prevent="check"
				/>
				<Button variant="solid" :loading="checking" :disabled="!canCheck" @click="check">
					{{ __('Check') }}
				</Button>
			</div>
			<ErrorMessage :message="checkError || (showErrors ? errors.gstin : '')" />

			<!-- the GSTIN is already a customer's: nothing new is created -->
			<template v-if="isChecked && g.existing.length">
				<p class="text-base text-ink-gray-7">
					{{
						g.existing.length > 1
							? __(
									'These customers already have this GSTIN. Choose the one this deal is for:'
							  )
							: __(
									'This GSTIN belongs to an existing customer. No new customer will be created.'
							  )
					}}
				</p>
				<label
					v-for="c in g.existing"
					:key="c.customer"
					class="flex cursor-pointer gap-3 rounded border p-3"
					:class="
						g.customer === c.customer
							? 'border-outline-gray-5 bg-surface-gray-1'
							: 'border-outline-gray-2'
					"
				>
					<input v-model="g.customer" type="radio" class="mt-1" :value="c.customer" />
					<span class="min-w-0">
						<span class="font-medium text-ink-gray-9">{{ c.customer_name }}</span>
						<span v-if="c.customer !== c.customer_name" class="text-ink-gray-5">
							({{ c.customer }})</span
						>
						<span v-if="c.disabled" class="text-ink-amber-3">
							· {{ __('Disabled') }}</span
						>
						<span class="mt-1 block text-sm text-ink-gray-6">{{
							summaryLine(c)
						}}</span>
					</span>
				</label>
				<ErrorMessage
					v-if="showErrors && errors.gstin_customer"
					:message="errors.gstin_customer"
				/>
			</template>

			<!-- a new customer: what the GST portal has for this GSTIN -->
			<div
				v-else-if="isChecked && g.registered"
				class="space-y-1 rounded border border-outline-gray-2 p-3 text-base"
			>
				<p class="font-medium text-ink-gray-9">
					{{ g.registered.business_name || g.checked }}
				</p>
				<p class="text-ink-gray-6">{{ addressLine(g.registered.address) }}</p>
				<p class="text-sm text-ink-gray-5">
					{{
						[g.registered.gst_category, g.registered.status]
							.filter(Boolean)
							.join(' · ')
					}}
				</p>
				<p v-if="inactive" class="text-sm text-ink-amber-3">
					{{ __('The GST portal shows this GSTIN as {0}.', [g.registered.status]) }}
				</p>
				<p class="pt-1 text-sm text-ink-gray-5">
					{{
						__(
							'New customer: the name and address are filled in on the next step and the customer is created after the review. The GST portal has no phone numbers or emails, so the contact comes from the lead.'
						)
					}}
				</p>
			</div>
		</template>
	</div>
</template>

<script setup>
import { computed, inject, ref, toRef, watch } from 'vue'
import { Button, ErrorMessage, FormControl, Switch } from 'frappe-ui'
import { api, errorMessage } from '@/lib/api'
import { GSTIN_FORMAT } from '@/lib/validation'
import { __ } from '@/translation'

const GST_GATE_KEY = 'gst_registered'

const w = inject('wizard')
const { ctx, form } = w
const errors = toRef(w, 'errors')
const showErrors = toRef(w, 'showErrors')
const g = form.gstin

const normalized = (value) => (value || '').trim().toUpperCase()
const canCheck = computed(() => GSTIN_FORMAT.test(normalized(g.value)))
const isChecked = computed(() => !!g.checked && g.checked === normalized(g.value))
const inactive = computed(() => {
	const status = (g.registered?.status || '').toLowerCase()
	return !!status && status !== 'active'
})

const checking = ref(false)
const checkError = ref('')
const loadingMatches = ref(false)

const NEW = '__new__'
const choice = computed({
	get: () => g.customer || (g.newCustomer ? NEW : ''),
	set: (value) => {
		g.customer = value === NEW ? '' : value
		g.newCustomer = value === NEW
		if (g.newCustomer) answerNoGst()
	},
})
const choiceClass = (value) =>
	choice.value === value ? 'border-outline-gray-5 bg-surface-gray-1' : 'border-outline-gray-2'

function reset() {
	g.checked = ''
	g.existing = []
	g.customer = ''
	g.newCustomer = false
	g.registered = null
	checkError.value = ''
}

/** No GSTIN: find the customers the lead may already be; none found means a new customer. */
async function loadMatches() {
	loadingMatches.value = true
	try {
		g.existing = await api('pranera_crm.erpnext_customer.customers_for_lead', {
			lead: ctx.lead.name,
		})
		if (!g.existing.length) {
			g.newCustomer = true
			answerNoGst()
		}
	} catch (err) {
		checkError.value = errorMessage(err)
	} finally {
		loadingMatches.value = false
	}
}

/** A new customer without a GSTIN is unregistered unless the sales person says otherwise. */
function answerNoGst() {
	const customer = form.customer
	const hasGstGate = (ctx.customer?.organization_questions || []).some(
		(q) => q.question_key === GST_GATE_KEY
	)
	if (customer.enabled && hasGstGate && customer.answers[GST_GATE_KEY] !== 'outside') {
		customer.answers[GST_GATE_KEY] = 'no'
	}
	if (customer.address.values.gstin) customer.address.values.gstin = ''
}

// a changed GSTIN, or "No GSTIN", drops the earlier result
watch(
	() => normalized(g.value),
	(value) => {
		if (g.checked && g.checked !== value) reset()
	}
)
watch(
	() => g.none,
	(none) => {
		reset()
		if (none) loadMatches()
	}
)

async function check() {
	if (checking.value || !canCheck.value) return
	checking.value = true
	checkError.value = ''
	try {
		const res = await api('pranera_crm.erpnext_customer.check_gstin', {
			gstin: normalized(g.value),
		})
		g.value = res.gstin
		g.checked = res.gstin
		g.existing = res.existing || []
		g.customer = g.existing.length === 1 ? g.existing[0].customer : ''
		g.registered = res.registered || null
		if (g.registered) applyRegistered(res.gstin, g.registered)
	} catch (err) {
		reset()
		checkError.value = errorMessage(err)
	} finally {
		checking.value = false
	}
}

/** A new customer: carry the GST portal's name and address into the Organization step. */
function applyRegistered(gstin, info) {
	const org = form.organization
	const customer = form.customer
	org.mode = 'new'
	org.existing = ''
	if (info.business_name) org.values.organization = info.business_name
	if (!customer.enabled) return
	const hasGstGate = (ctx.customer?.organization_questions || []).some(
		(q) => q.question_key === GST_GATE_KEY
	)
	if (hasGstGate) customer.answers[GST_GATE_KEY] = 'yes'
	customer.address.mode = 'new'
	customer.address.existing = ''
	customer.address.values.gstin = gstin
	for (const [field, value] of Object.entries(info.address || {})) {
		if (value && field in customer.address.values) customer.address.values[field] = value
	}
}

const addressLine = (a) =>
	[a?.address_line1, a?.address_line2, a?.city, a?.state, a?.pincode].filter(Boolean).join(', ')

function summaryLine(c) {
	const parts = []
	const address = c.addresses?.[0]
	if (address) parts.push(addressLine(address))
	if (c.sales_persons?.length) parts.push(__('Sales: {0}', [c.sales_persons.join(', ')]))
	parts.push(
		c.contacts?.length === 1 ? __('1 contact') : __('{0} contacts', [c.contacts?.length || 0])
	)
	return parts.join(' · ')
}
</script>
