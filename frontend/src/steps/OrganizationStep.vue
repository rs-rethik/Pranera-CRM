<template>
	<div class="space-y-4">
		<h2 class="text-center text-xl font-semibold text-ink-gray-9">{{ __('Organization') }}</h2>

		<Switch v-model="useExisting" :label="__('Choose Existing')" />

		<template v-if="useExisting">
			<CandidateList
				v-if="candidates.organizations?.length"
				:candidates="candidates.organizations"
				:selected="org.existing"
				@select="(name) => (org.existing = name)"
			>
				<template #default="{ candidate }">
					<span class="min-w-0">
						<span class="font-medium text-ink-gray-9">{{
							candidate.organization_name
						}}</span>
						<span class="text-ink-gray-5">
							—
							{{
								candidate.exact
									? __('Exact match with the lead')
									: __("Matches the lead's {0}", [matchReason(candidate.reason)])
							}}
						</span>
					</span>
				</template>
			</CandidateList>

			<Link
				v-model="org.existing"
				doctype="CRM Organization"
				:label="
					candidates.organizations?.length
						? __('Or search for another organization')
						: __('Organization')
				"
				:placeholder="__('Search organization')"
				:description="matchNote"
				required
				:error="showErrors ? errors.existing : ''"
			/>
		</template>

		<template v-if="!useExisting">
			<!-- answered on the GSTIN step; asked here only if that couldn't answer it -->
			<template v-if="customerTypeGateActive && customerTypeAnswer == null">
				<QuestionField
					v-model="customer.answers[customerTypeGateQuestion.question_key]"
					:question="customerTypeGateQuestion"
					:error="
						showErrors ? errors['cq_' + customerTypeGateQuestion.question_key] : ''
					"
				/>
			</template>

			<template
				v-if="customerTypeUnlocked && gstGateActive && !ctx.customer.existing_customer"
			>
				<QuestionField
					v-if="gstAnswer == null"
					v-model="customer.answers[gstGateQuestion.question_key]"
					:question="gstGateQuestion"
					:error="showErrors ? errors['cq_' + gstGateQuestion.question_key] : ''"
				/>

				<template v-if="gstAnswer === 'yes'">
					<div v-if="gstChildQuestions.length" class="grid grid-cols-2 gap-x-4 gap-y-4">
						<QuestionField
							v-for="q in gstChildQuestions"
							:key="q.question_key"
							v-model="customer.answers[q.question_key]"
							:question="q"
							:error="showErrors ? errors['cq_' + q.question_key] : ''"
						/>
					</div>
				</template>
			</template>

			<template v-if="orgDetailsUnlocked">
				<div v-if="!isIndividual" class="grid grid-cols-2 gap-x-4 gap-y-4">
					<FieldControl
						v-for="field in ctx.organization_fields"
						:key="field.fieldname"
						v-model="org.values[field.fieldname]"
						:field="
							orgNameLocked && field.fieldname === 'organization'
								? {
										...field,
										description: __('Auto-filled from the GSTIN above.'),
								  }
								: field
						"
						:disabled="orgNameLocked && field.fieldname === 'organization'"
						:class="
							field.fieldname === 'organization' || field.fieldname === 'website'
								? 'col-span-2'
								: ''
						"
						:error="showErrors ? errors[field.fieldname] : ''"
					/>
				</div>

				<div
					v-if="bridgeIndependentOrgQuestions.length"
					class="grid grid-cols-2 gap-x-4 gap-y-4"
				>
					<QuestionField
						v-for="q in bridgeIndependentOrgQuestions"
						:key="q.question_key"
						v-model="customer.answers[q.question_key]"
						:question="q"
						:error="showErrors ? errors['cq_' + q.question_key] : ''"
					/>
				</div>

				<p v-if="isIndividual" class="text-sm text-ink-gray-5">
					{{
						__(
							'No organization will be created — the customer will be named after the contact.'
						)
					}}
				</p>
				<p v-else-if="candidates.auto_organization" class="text-sm text-ink-gray-5">
					{{
						__(
							'"{0}" already exists, so CRM will link it instead of creating a new organization.',
							[candidates.auto_organization]
						)
					}}
				</p>
				<p v-else class="text-sm text-ink-gray-5">
					{{
						__(
							'A new organization is created from these details. Leave the name empty to convert without one.'
						)
					}}
				</p>

				<template v-if="ctx.customer?.enabled">
					<div class="h-px bg-outline-gray-2" />

					<h3 class="text-base font-medium text-ink-gray-8">
						{{ __('Customer details (ERPNext)') }}
					</h3>

					<template v-if="customer.enabled">
						<p v-if="ctx.customer.existing_customer" class="text-sm text-ink-gray-5">
							{{
								__('Already linked to Customer {0}.', [
									ctx.customer.existing_customer,
								])
							}}
						</p>

						<template v-else>
							<div class="grid grid-cols-2 gap-x-4 gap-y-4">
								<QuestionField
									v-for="q in remainingOrganizationQuestions"
									:key="q.question_key"
									v-model="customer.answers[q.question_key]"
									:question="q"
									:error="showErrors ? errors['cq_' + q.question_key] : ''"
								/>
							</div>

							<h3 class="text-base font-medium text-ink-gray-8">
								{{ __('Address') }}
							</h3>

							<Switch
								v-if="!addressLocked"
								v-model="addressUseExisting"
								:label="__('Choose Existing')"
							/>

							<Link
								v-if="addressUseExisting && !addressLocked"
								v-model="customer.address.existing"
								doctype="Address"
								:label="__('Address')"
								:placeholder="__('Search address')"
								required
								:error="showErrors ? errors.customer_existing_address : ''"
							/>

							<!-- from the GST portal: shown as it is -->
							<template v-else-if="addressLocked">
								<div class="grid grid-cols-2 gap-x-4 gap-y-4">
									<FieldControl
										v-for="field in otherAddressFields"
										:key="field.fieldname"
										v-model="customer.address.values[field.fieldname]"
										:field="addressField(field)"
										:disabled="addressLocked"
										:class="
											['address_line1', 'address_line2'].includes(
												field.fieldname
											)
												? 'col-span-2'
												: ''
										"
										:error="
											showErrors ? errors['customer_' + field.fieldname] : ''
										"
									/>
								</div>
							</template>

							<!-- typed: the pincode fills the state and suggests the city -->
							<template v-else>
								<div class="grid grid-cols-2 gap-x-4 gap-y-4">
									<FormControl
										v-model="address.pincode"
										type="text"
										inputmode="numeric"
										maxlength="6"
										autocomplete="postal-code"
										:label="__('Pincode')"
										placeholder="641604"
										:required="addressRequired"
										:description="pincodeNote"
										:error="
											pincodeError ||
											(showErrors ? errors.customer_pincode : '')
										"
									/>
									<Combobox
										v-model="cityModel"
										:options="cityOptions"
										:label="__('City')"
										:placeholder="__('Pick or type the city')"
										:required="addressRequired"
										open-on-focus
										:error="showErrors ? errors.customer_city : ''"
									/>
									<Combobox
										v-model="stateModel"
										:options="stateOptions"
										:label="__('State')"
										:placeholder="__('Pick the state')"
										:required="addressRequired && address.country === 'India'"
										open-on-focus
										:error="showErrors ? errors.customer_state : ''"
									/>
									<Link
										v-model="address.country"
										doctype="Country"
										:label="__('Country')"
										:required="addressRequired"
										:error="showErrors ? errors.customer_country : ''"
									/>
									<FormControl
										v-model="address.address_line1"
										type="text"
										class="col-span-2"
										autocomplete="address-line1"
										:label="__('Address Line 1')"
										:placeholder="__('Door no., street')"
										:required="addressRequired"
										:error="showErrors ? errors.customer_address_line1 : ''"
									/>
									<FormControl
										v-model="address.address_line2"
										type="text"
										class="col-span-2"
										autocomplete="address-line2"
										:label="__('Address Line 2')"
										:placeholder="__('Area, landmark (optional)')"
									/>
								</div>
								<p class="text-sm text-ink-gray-5">
									{{
										addressRequired
											? __(
													"Required: with no GSTIN, the customer's address is entered here."
											  )
											: __('Optional — leave the address blank to skip it.')
									}}
								</p>
							</template>
						</template>
					</template>
				</template>
			</template>
		</template>
	</div>
</template>

<script setup>
import { computed, inject, ref, toRef, watch } from 'vue'
import { Combobox, FormControl, Switch } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import CandidateList from '@/components/CandidateList.vue'
import FieldControl from '@/components/FieldControl.vue'
import QuestionField from '@/components/QuestionField.vue'
import { useDynamicOptionsRefresh } from '@/composables/useDynamicOptionsRefresh'
import { api, errorMessage } from '@/lib/api'
import { matchReason } from '@/lib/layout'
import { descendantKeys, visibleQuestions } from '@/lib/questions'
import { needsAddress } from '@/lib/validation'
import { __ } from '@/translation'

const w = inject('wizard')
const { ctx, form } = w
const candidates = toRef(w, 'candidates')
const errors = toRef(w, 'errors')
const showErrors = toRef(w, 'showErrors')
const org = form.organization
const customer = form.customer

const useExisting = computed({
	get: () => org.mode === 'existing',
	set: (on) => {
		org.mode = on ? 'existing' : 'new'
		if (on && !org.existing) {
			org.existing =
				candidates.value.auto_organization ||
				candidates.value.organizations?.[0]?.name ||
				''
		}
	},
})

const addressRequired = computed(() => needsAddress(form))
// with no GSTIN these make the customer's address: marked required like the server-side ones
const REQUIRED_ADDRESS = ['address_line1', 'city', 'pincode', 'country']
function addressField(field) {
	if (addressLocked.value)
		return { ...field, description: __('Auto-filled from the GSTIN above.') }
	const required =
		REQUIRED_ADDRESS.includes(field.fieldname) ||
		(field.fieldname === 'state' && customer.address.values.country === 'India')
	return addressRequired.value && required ? { ...field, reqd: 1 } : field
}
const addressUseExisting = computed({
	get: () => customer.address.mode === 'existing',
	set: (on) => {
		customer.address.mode = on ? 'existing' : 'new'
	},
})

const matchNote = computed(() => {
	const match = (candidates.value.organizations || []).find((o) => o.name === org.existing)
	return match
		? match.exact
			? __('Exact match with the lead')
			: __("Matches the lead's {0}", [matchReason(match.reason)])
		: ''
})

const organizationQuestions = computed(() =>
	visibleQuestions(ctx.customer?.organization_questions, customer.answers)
)

useDynamicOptionsRefresh(
	'Organization',
	computed(() => ctx.customer?.organization_questions),
	customer.answers,
	computed(() => !!ctx.customer?.enabled)
)

const INDIVIDUAL_GATE_KEY = 'customer_type'
const INDIVIDUAL_OPTION_VALUE = 'individual'

const customerTypeGateQuestion = computed(() =>
	(ctx.customer?.organization_questions || []).find(
		(q) => q.question_key === INDIVIDUAL_GATE_KEY
	)
)
const customerTypeAnswer = computed(() => customer.answers[INDIVIDUAL_GATE_KEY])
const customerTypeGateActive = computed(() => !!customerTypeGateQuestion.value)
const customerTypeUnlocked = computed(
	() => !customerTypeGateActive.value || customerTypeAnswer.value != null
)
const isIndividual = computed(() => customerTypeAnswer.value === INDIVIDUAL_OPTION_VALUE)

watch(isIndividual, (now) => {
	if (!now) return
	org.values.organization = ''
	org.values.website = ''
	org.values.annual_revenue = ''
	org.values.no_of_employees = ''
})

const GST_GATE_KEY = 'gst_registered'

const gstGateQuestion = computed(() =>
	(ctx.customer?.organization_questions || []).find((q) => q.question_key === GST_GATE_KEY)
)
const gstAnswer = computed(() => customer.answers[GST_GATE_KEY])
const gstGateActive = computed(() => !!gstGateQuestion.value)

const gstChildKeys = computed(() =>
	gstGateActive.value
		? descendantKeys(ctx.customer?.organization_questions, GST_GATE_KEY)
		: new Set()
)
const gstChildQuestions = computed(() =>
	organizationQuestions.value.filter((q) => gstChildKeys.value.has(q.question_key))
)

const orgDetailsUnlocked = computed(
	() => customerTypeUnlocked.value && (!gstGateActive.value || gstAnswer.value != null)
)

// a GSTIN checked on the first step: the GST portal's name and address are used as they are
const fromGstPortal = computed(() => !form.gstin.none && !!form.gstin.registered)
const orgNameLocked = computed(
	() =>
		(gstGateActive.value && gstAnswer.value === 'yes') ||
		(fromGstPortal.value && !!org.values.organization)
)
const addressLocked = computed(
	() =>
		(gstGateActive.value && gstAnswer.value === 'yes') ||
		(fromGstPortal.value && !!customer.address.values.address_line1)
)

const GATE_KEYS = new Set([INDIVIDUAL_GATE_KEY, GST_GATE_KEY])

const bridgeIndependentOrgQuestions = computed(() =>
	organizationQuestions.value.filter(
		(q) =>
			!q.requires_erpnext_bridge &&
			!GATE_KEYS.has(q.question_key) &&
			!gstChildKeys.value.has(q.question_key)
	)
)
const remainingOrganizationQuestions = computed(() =>
	organizationQuestions.value.filter(
		(q) =>
			q.requires_erpnext_bridge &&
			!GATE_KEYS.has(q.question_key) &&
			!gstChildKeys.value.has(q.question_key)
	)
)

const otherAddressFields = computed(() =>
	(ctx.customer?.address_fields || []).filter((f) => f.fieldname !== 'gstin')
)

// ---- typed address: the pincode fills the state and suggests the city ----
const address = customer.address.values
if (!address.country) address.country = 'India'

const pincodeInfo = ref(null)
const pincodeError = ref('')
const lookingUp = ref(false)
const PINCODE = /^[1-9][0-9]{5}$/

watch(
	() => (address.pincode || '').trim(),
	async (pincode) => {
		pincodeError.value = ''
		if (!PINCODE.test(pincode)) {
			pincodeInfo.value = null
			return
		}
		if (address.country && address.country !== 'India') return
		lookingUp.value = true
		try {
			const info = await api('pranera_crm.pincode.pincode_details', { pincode })
			if ((address.pincode || '').trim() !== pincode) return // typed on meanwhile
			pincodeInfo.value = info
			if (info.state) address.state = info.state
			else if (info.states?.length && !info.states.includes(address.state))
				address.state = ''
			const known = info.cities.map((c) => c.toLowerCase())
			if (info.cities.length && !known.includes((address.city || '').toLowerCase()))
				address.city = info.cities[0]
		} catch (err) {
			pincodeError.value = errorMessage(err)
		} finally {
			lookingUp.value = false
		}
	},
	{ immediate: true }
)

const pincodeNote = computed(() => {
	if (lookingUp.value) return __('Looking up the pincode...')
	const info = pincodeInfo.value
	if (!info) return __('Enter the 6-digit pincode: the state and city are filled in.')
	if (!info.cities.length) return __('Pincode not found: pick the state and type the city.')
	return info.cities.length > 1
		? __('City filled in; {0} more to pick from.', [info.cities.length - 1])
		: __('City and state filled in.')
})

const asOptions = (names) => names.map((name) => ({ label: name, value: name }))
const cityOptions = computed(() => [
	...asOptions(pincodeInfo.value?.cities || []),
	{
		type: 'custom',
		key: 'typed-city',
		label: __('Use the typed name'),
		keepOpen: false,
		condition: ({ query }) => {
			const q = (query || '').trim().toLowerCase()
			return !!q && !(pincodeInfo.value?.cities || []).some((c) => c.toLowerCase() === q)
		},
		onClick: ({ query }) => {
			address.city = (query || '').trim()
		},
	},
])
const cityModel = computed({
	get: () => address.city || null,
	set: (value) => {
		address.city = value || ''
	},
})

// the pincode's states first (Chandigarh's pincodes are Punjab's too), then every other state
const stateOptions = computed(() => {
	const first = pincodeInfo.value?.states || []
	const rest = (ctx.customer?.india_states || []).filter((s) => !first.includes(s))
	return asOptions([...first, ...rest])
})
const stateModel = computed({
	get: () => address.state || null,
	set: (value) => {
		address.state = value || ''
	},
})
</script>
