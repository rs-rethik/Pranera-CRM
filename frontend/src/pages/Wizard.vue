<template>
	<main
		class="min-h-dvh bg-surface-base px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(2rem,env(safe-area-inset-top))] sm:pt-[8vh]"
	>
		<div class="mx-auto w-full max-w-3xl">
			<StepDots v-if="active" :total="STEPS.length" :current="stepIndex" />

			<div
				class="rounded-lg border border-outline-gray-2 bg-surface-base p-5 sm:px-10 sm:py-8"
			>
				<LoadingText v-if="loading" class="justify-center" :text="__('Loading...')" />

				<div v-else-if="loadError" class="space-y-4">
					<ErrorMessage :message="loadError" />
					<div class="flex justify-end gap-2">
						<a :href="crmHref"
							><Button variant="subtle">{{ __('Open CRM') }}</Button></a
						>
						<Button variant="solid" @click="load">{{ __('Try again') }}</Button>
					</div>
				</div>

				<div v-else-if="wizard.ctx?.converted" class="space-y-4 text-center">
					<h2 class="text-xl font-semibold text-ink-gray-9">
						{{ __('Already converted') }}
					</h2>
					<p class="text-base text-ink-gray-6">
						{{
							wizard.ctx.deal
								? __('This lead was converted to deal {0}.', [wizard.ctx.deal])
								: __('This lead has already been converted.')
						}}
					</p>
					<a :href="wizard.ctx.deal ? dealHref(wizard.ctx.deal) : leadHref">
						<Button variant="solid">{{
							wizard.ctx.deal ? __('Open deal') : __('Open lead')
						}}</Button>
					</a>
				</div>

				<div v-else-if="wizard.ctx?.lost" class="space-y-4 text-center">
					<h2 class="text-xl font-semibold text-ink-gray-9">
						{{ __("Can't convert") }}
					</h2>
					<p class="text-base text-ink-gray-6">
						{{ __("Leads with a lost status can't be converted.") }}
					</p>
					<a :href="leadHref"
						><Button variant="solid">{{ __('Open lead') }}</Button></a
					>
				</div>

				<div v-else-if="wizard.ctx && !wizard.ctx.can_write" class="space-y-4 text-center">
					<h2 class="text-xl font-semibold text-ink-gray-9">
						{{ __("Can't convert") }}
					</h2>
					<p class="text-base text-ink-gray-6">
						{{ __('You have read-only access to this lead.') }}
					</p>
					<a :href="leadHref"
						><Button variant="solid">{{ __('Open lead') }}</Button></a
					>
				</div>

				<div v-else-if="customerFollowUp" class="space-y-4">
					<h2 class="text-xl font-semibold text-ink-gray-9">
						{{ __('Deal converted') }}
					</h2>

					<template v-if="customerFollowUp.type === 'duplicate'">
						<p class="text-base text-ink-gray-6">
							{{
								__('A customer named "{0}" already exists.', [
									customerFollowUp.existingCustomer,
								])
							}}
						</p>
						<div class="flex flex-wrap gap-2">
							<Button
								variant="solid"
								:loading="followUpBusy"
								@click="confirmDuplicateCustomer"
							>
								{{ __('Use existing customer') }}
							</Button>
							<a :href="dealHref(customerFollowUp.deal)"
								><Button variant="subtle">{{ __('Skip for now') }}</Button></a
							>
						</div>
					</template>

					<template v-else>
						<ErrorMessage :message="customerFollowUp.message" />
						<div class="flex flex-wrap gap-2">
							<Button
								variant="solid"
								:loading="followUpBusy"
								@click="retryCustomerSetup"
								>{{ __('Try again') }}</Button
							>
							<Button
								variant="subtle"
								:disabled="followUpBusy"
								@click="editAndRetry"
								>{{ __('Edit details') }}</Button
							>
							<a :href="dealHref(customerFollowUp.deal)"
								><Button variant="subtle">{{ __('Continue to deal') }}</Button></a
							>
						</div>
					</template>
				</div>

				<template v-else-if="active">
					<p v-if="draftInfo" class="mb-4 text-sm text-ink-gray-5">
						{{ __('Draft restored from {0}.', [savedAgo(draftInfo.savedAt)]) }}
						<span v-if="draftInfo.leadChanged">{{
							__('The lead has changed since, so check the values.')
						}}</span>
						<button type="button" class="underline" @click="startOver">
							{{ __('Start over') }}
						</button>
					</p>

					<component :is="STEP_COMPONENTS[stepIndex]" @edit="goTo" />

					<p v-if="!online" class="mt-4 text-sm text-ink-amber-3" role="status">
						{{
							__(
								"You're offline. Your draft is saved on this device; reconnect to convert."
							)
						}}
					</p>
					<div ref="errorBox"><ErrorMessage class="mt-4" :message="submitError" /></div>

					<div
						v-if="!isLast && !stepValid"
						class="mt-4 text-sm text-ink-gray-5"
						role="status"
					>
						<p>{{ __('Complete the required fields to continue:') }}</p>
						<ul class="mt-1 list-disc ps-5">
							<li v-for="message in stepProblems" :key="message">{{ message }}</li>
						</ul>
					</div>

					<div
						class="mt-6 flex items-center"
						:class="stepIndex > 0 ? 'justify-between' : 'justify-end'"
					>
						<Button
							v-if="stepIndex > 0"
							variant="subtle"
							:disabled="submitting"
							@click="back"
							>{{ __('Back') }}</Button
						>
						<Button
							v-if="!isLast"
							variant="solid"
							:disabled="!stepValid"
							@click="next"
							>{{ __('Next') }}</Button
						>
						<Button
							v-else
							variant="solid"
							:loading="submitting"
							:disabled="!online || submitting"
							@click="submit"
						>
							{{ retryDeal ? __('Save and try again') : __('Convert to Deal') }}
						</Button>
					</div>
				</template>
			</div>
		</div>
	</main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, LoadingText } from 'frappe-ui'
import StepDots from '@/components/StepDots.vue'
import { useOnline } from '@/composables/useOnline'
import { api, errorMessage } from '@/lib/api'
import { debounce } from '@/lib/debounce'
import { clearDraft, loadDraft, saveDraft, saveDraftSync } from '@/lib/drafts'
import { applyDraft, createForm, customerPayload, toPayload } from '@/lib/form'
import { STEPS, isStepValid, resolveStep, validateStep } from '@/lib/validation'
import { __ } from '@/translation'
import ContactStep from '@/steps/ContactStep.vue'
import DealStep from '@/steps/DealStep.vue'
import OrganizationStep from '@/steps/OrganizationStep.vue'
import ReviewStep from '@/steps/ReviewStep.vue'

const props = defineProps({ name: { type: String, required: true } })

const STEP_COMPONENTS = [OrganizationStep, ContactStep, DealStep, ReviewStep]

const route = useRoute()
const router = useRouter()
const online = useOnline()
const user = window.pranera_user

const wizard = reactive({
	ctx: null,
	form: null,
	candidates: { organizations: [], contacts: [], auto_organization: null, auto_contact: null },
	errors: computed(() =>
		active.value ? validateStep(stepIndex.value, wizard.form, wizard.ctx) : {}
	),
	showErrors: false,
})
provide('wizard', wizard)

const loading = ref(true)
const loadError = ref('')
const ready = ref(false)
const stepIndex = ref(0)
const submitting = ref(false)
const submitError = ref('')
const draftInfo = ref(null)
const errorBox = ref(null)
const customerFollowUp = ref(null)
const followUpBusy = ref(false)
const retryDeal = ref(null)
let finished = false
let draftStep = null

const active = computed(() => ready.value && !!wizard.form)
const isLast = computed(() => stepIndex.value === STEPS.length - 1)
const stepProblems = computed(() => [...new Set(Object.values(wizard.errors || {}))])
const stepValid = computed(() => !active.value || stepProblems.value.length === 0)
const leadHref = computed(() => `/crm/leads/${encodeURIComponent(props.name)}`)
const crmHref = '/crm'
const dealHref = (deal) => `/crm/deals/${encodeURIComponent(deal)}`

async function load() {
	loading.value = true
	loadError.value = ''
	ready.value = false
	wizard.form = null
	try {
		const ctx = await api('pranera_crm.api.get_wizard_context', { lead: props.name })
		wizard.ctx = ctx

		if (ctx.converted) {
			await clearDraft(user, props.name)
			return
		}
		if (ctx.lost || !ctx.can_write) return

		wizard.candidates = ctx.candidates
		wizard.form = createForm(ctx)

		const draft = await loadDraft(user, props.name)
		if (draft) {
			applyDraft(wizard.form, draft)
			draftStep = draft.step
			draftInfo.value = {
				savedAt: draft.savedAt,
				leadChanged: !!draft.modified && draft.modified !== ctx.lead.modified,
			}
		}

		ready.value = true
		syncStep()
	} catch (err) {
		wizard.ctx = null
		loadError.value = errorMessage(err)
	} finally {
		loading.value = false
	}
}

function syncStep() {
	if (!active.value) return
	const requested = route.query.step ?? draftStep
	draftStep = null
	const index = resolveStep(requested, wizard.form, wizard.ctx)
	stepIndex.value = index
	if (String(route.query.step) !== String(index + 1)) {
		router.replace({ query: { ...route.query, step: index + 1 } })
	}
}

watch(() => route.query.step, syncStep)
watch(stepIndex, () => {
	wizard.showErrors = false
	window.scrollTo({ top: 0 })
})

function goTo(index, { replace = false } = {}) {
	const target = { query: { ...route.query, step: index + 1 } }
	return replace ? router.replace(target) : router.push(target)
}

function next() {
	if (!isStepValid(stepIndex.value, wizard.form, wizard.ctx)) {
		wizard.showErrors = true
		nextTick(() =>
			document
				.querySelector('[aria-invalid="true"]')
				?.scrollIntoView({ block: 'center', behavior: 'smooth' })
		)
		return
	}
	goTo(stepIndex.value + 1)
}

function back() {
	const previous = window.history.state?.back
	const previousStep = previous
		? new URL(previous, window.location.origin).searchParams.get('step')
		: null
	if (previousStep === String(stepIndex.value)) router.back()
	else goTo(stepIndex.value - 1, { replace: true })
}

const refreshCandidates = debounce(async () => {
	if (!active.value || !online.value || finished) return
	const org = wizard.form.organization.values
	const contact = wizard.form.contact.values
	try {
		wizard.candidates = await api('pranera_crm.api.search_candidates', {
			lead: props.name,
			organization: org.organization,
			website: org.website,
			email: contact.email,
			phone: contact.phone,
			mobile_no: contact.mobile_no,
		})
	} catch {
		/* noop */
	}
}, 600)

watch(
	() => {
		if (!wizard.form) return null
		const { organization, website } = wizard.form.organization.values
		const { email, phone, mobile_no } = wizard.form.contact.values
		return [organization, website, email, phone, mobile_no].join('\u0000')
	},
	(value, old) => {
		if (old !== null) refreshCandidates()
	}
)

function snapshot() {
	return {
		form: JSON.parse(JSON.stringify(wizard.form)),
		step: stepIndex.value + 1,
		modified: wizard.ctx?.lead?.modified || null,
	}
}

const persist = debounce(() => {
	if (active.value && !finished) saveDraft(user, props.name, snapshot())
}, 500)

watch([() => wizard.form, stepIndex], () => persist(), { deep: true })

function flushDraft() {
	if (!active.value || finished) return
	saveDraftSync(user, props.name, snapshot())
	persist.flush()
}
const flushIfHidden = () => document.visibilityState === 'hidden' && flushDraft()
onMounted(() => {
	document.addEventListener('visibilitychange', flushIfHidden)
	window.addEventListener('pagehide', flushDraft)
})
onBeforeUnmount(() => {
	document.removeEventListener('visibilitychange', flushIfHidden)
	window.removeEventListener('pagehide', flushDraft)
	persist.flush()
})

async function startOver() {
	persist.cancel()
	await clearDraft(user, props.name)
	draftInfo.value = null
	wizard.form = createForm(wizard.ctx)
	wizard.candidates = wizard.ctx.candidates
	goTo(0, { replace: true })
}

function savedAgo(timestamp) {
	const minutes = Math.round((Date.now() - timestamp) / 60000)
	if (minutes < 1) return __('a moment ago')
	if (minutes < 60) return __('{0} min ago', [minutes])
	const hours = Math.round(minutes / 60)
	if (hours < 24) return __('{0} h ago', [hours])
	return __('{0} d ago', [Math.round(hours / 24)])
}

async function submit() {
	if (submitting.value || !online.value) return

	for (let i = 0; i < STEPS.length - 1; i++) {
		if (!isStepValid(i, wizard.form, wizard.ctx)) {
			goTo(i)
			wizard.showErrors = true
			return
		}
	}

	submitting.value = true
	submitError.value = ''
	try {
		const response = retryDeal.value
			? await api('pranera_crm.api.setup_customer_for_deal', {
					deal: retryDeal.value,
					...customerPayload(wizard.form),
			  })
			: await api('pranera_crm.api.convert', toPayload(wizard.form, props.name))
		finished = true
		persist.cancel()
		await clearDraft(user, props.name)
		handleConvertResponse(response, retryDeal.value)
	} catch (err) {
		if (err?.exc_type === 'LeadAlreadyConverted') {
			finished = true
			persist.cancel()
			await clearDraft(user, props.name)
			await load()
			submitting.value = false
			return
		}
		submitError.value = errorMessage(err)
		submitting.value = false
		await nextTick()
		errorBox.value?.scrollIntoView({ block: 'center', behavior: 'smooth' })
	}
}

function handleConvertResponse(response, dealOverride) {
	submitting.value = false
	const deal = dealOverride || response.deal
	if (response.duplicate_customer) {
		customerFollowUp.value = {
			type: 'duplicate',
			deal,
			existingCustomer: response.duplicate_customer,
		}
		return
	}
	if (response.customer_error) {
		customerFollowUp.value = { type: 'error', deal, message: response.customer_error }
		return
	}
	window.location.assign(dealHref(deal))
}

async function confirmDuplicateCustomer() {
	followUpBusy.value = true
	const deal = customerFollowUp.value.deal
	try {
		await api('pranera_crm.api.setup_customer_for_deal', {
			deal,
			...customerPayload(wizard.form),
			confirm_duplicate_customer: true,
		})
		customerFollowUp.value = null
		window.location.assign(dealHref(deal))
	} catch (err) {
		customerFollowUp.value = { type: 'error', deal, message: errorMessage(err) }
	} finally {
		followUpBusy.value = false
	}
}

async function retryCustomerSetup() {
	followUpBusy.value = true
	const deal = customerFollowUp.value.deal
	try {
		const response = await api('pranera_crm.api.setup_customer_for_deal', {
			deal,
			...customerPayload(wizard.form),
		})
		if (response.duplicate_customer) {
			customerFollowUp.value = {
				type: 'duplicate',
				deal,
				existingCustomer: response.duplicate_customer,
			}
		} else if (response.customer_error) {
			customerFollowUp.value = { type: 'error', deal, message: response.customer_error }
		} else {
			customerFollowUp.value = null
			window.location.assign(dealHref(deal))
		}
	} catch (err) {
		customerFollowUp.value = { type: 'error', deal, message: errorMessage(err) }
	} finally {
		followUpBusy.value = false
	}
}

function editAndRetry() {
	retryDeal.value = customerFollowUp.value.deal
	customerFollowUp.value = null
	wizard.showErrors = false
	goTo(0)
}

onMounted(load)
watch(
	() => props.name,
	() => {
		finished = false
		load()
	}
)
</script>
