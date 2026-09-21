<template>
  <div class="flex min-h-dvh flex-col bg-surface-gray-1">
    <AppHeader :subtitle="subtitle" :back-href="leadHref" back-label="Back to lead" />

    <div
      v-if="!online"
      class="flex items-center justify-center gap-2 bg-surface-amber-2 px-4 py-2 text-sm text-ink-amber-3"
      role="status"
    >
      <span class="lucide-wifi-off size-4" />
      You're offline. You can keep editing (your draft is saved on this device), but converting needs a connection.
    </div>

    <main class="mx-auto w-full max-w-2xl flex-1 px-4 pb-6 pt-4 sm:pt-8">
      <!-- loading -->
      <div v-if="loading" class="animate-pulse space-y-4" aria-busy="true" aria-label="Loading lead">
        <div class="h-6 w-1/2 rounded bg-surface-gray-3" />
        <div class="h-64 rounded-xl bg-surface-gray-2" />
      </div>

      <!-- couldn't load -->
      <div v-else-if="loadError" class="space-y-4">
        <NoticeBanner tone="error">{{ loadError }}</NoticeBanner>
        <div class="flex gap-2">
          <Button variant="subtle" @click="load">Try again</Button>
          <a :href="crmHref"><Button variant="ghost">Open CRM</Button></a>
        </div>
      </div>

      <!-- already converted -->
      <StatusCard
        v-else-if="wizard.ctx?.converted"
        icon="lucide-circle-check"
        title="This lead is already converted"
        :text="
          wizard.ctx.deal
            ? `It was converted to deal ${wizard.ctx.deal}.`
            : 'It has already been converted to a deal.'
        "
      >
        <a v-if="wizard.ctx.deal" :href="dealHref(wizard.ctx.deal)">
          <Button variant="solid" size="lg">Open deal</Button>
        </a>
        <a v-else :href="leadHref"><Button variant="solid" size="lg">Open lead</Button></a>
      </StatusCard>

      <StatusCard
        v-else-if="wizard.ctx?.lost"
        icon="lucide-circle-x"
        title="This lead can't be converted"
        text="Leads with a lost status can't be converted. Change the status in CRM first."
      >
        <a :href="leadHref"><Button variant="solid" size="lg">Open lead</Button></a>
      </StatusCard>

      <StatusCard
        v-else-if="wizard.ctx && !wizard.ctx.can_write"
        icon="lucide-lock"
        title="You can't convert this lead"
        text="You have read-only access to this lead."
      >
        <a :href="leadHref"><Button variant="solid" size="lg">Open lead</Button></a>
      </StatusCard>

      <!-- the wizard -->
      <template v-else-if="active">
        <StepIndicator :steps="STEPS" :current="stepIndex" :reachable="reachable" @select="goTo" />

        <NoticeBanner v-if="draftInfo" class="mt-4">
          Draft restored from {{ savedAgo(draftInfo.savedAt) }}.
          <span v-if="draftInfo.leadChanged">The lead has changed since then, so please double-check the values.</span>
          <template #action>
            <div class="flex shrink-0 gap-1">
              <Button size="sm" variant="ghost" @click="startOver">Start over</Button>
              <Button size="sm" variant="ghost" aria-label="Dismiss" @click="draftInfo = null">
                <span class="lucide-x size-4" />
              </Button>
            </div>
          </template>
        </NoticeBanner>

        <section class="mt-4 rounded-xl border border-outline-gray-2 bg-surface-white p-4 sm:p-6">
          <component :is="STEP_COMPONENTS[stepIndex]" @edit="goTo" />
        </section>

        <NoticeBanner v-if="submitError" ref="errorBox" tone="error" class="mt-4">
          {{ submitError }}
        </NoticeBanner>
      </template>
    </main>

    <footer
      v-if="active"
      class="sticky bottom-0 z-10 border-t border-outline-gray-2 bg-surface-white px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
    >
      <div class="mx-auto flex w-full max-w-2xl gap-3">
        <Button v-if="stepIndex > 0" class="!h-12 px-5" size="lg" variant="outline" :disabled="submitting" @click="back">
          Back
        </Button>
        <Button v-if="!isLast" class="!h-12 flex-1" size="lg" variant="solid" @click="next">Next</Button>
        <Button
          v-else
          class="!h-12 flex-1"
          size="lg"
          variant="solid"
          :loading="submitting"
          :disabled="!online || submitting"
          @click="submit"
        >
          Convert to Deal
        </Button>
      </div>
      <p v-if="isLast && !online" class="mt-2 text-center text-xs text-ink-gray-5">
        Reconnect to convert. Your draft is saved.
      </p>
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'
import NoticeBanner from '@/components/NoticeBanner.vue'
import StatusCard from '@/components/StatusCard.vue'
import StepIndicator from '@/components/StepIndicator.vue'
import { useOnline } from '@/composables/useOnline'
import { api, errorMessage } from '@/lib/api'
import { debounce } from '@/lib/debounce'
import { clearDraft, loadDraft, saveDraft, saveDraftSync } from '@/lib/drafts'
import { applyDraft, createForm, toPayload } from '@/lib/form'
import { STEPS, firstInvalidStep, isStepValid, resolveStep, validateStep } from '@/lib/validation'
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

// Shared with the step components (see steps/*.vue).
const wizard = reactive({
  ctx: null,
  form: null,
  candidates: { organizations: [], contacts: [], auto_organization: null, auto_contact: null },
  errors: computed(() => (active.value ? validateStep(stepIndex.value, wizard.form, wizard.ctx) : {})),
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
let finished = false
let draftStep = null

const active = computed(() => ready.value && !!wizard.form)
const isLast = computed(() => stepIndex.value === STEPS.length - 1)
const reachable = computed(() => (active.value ? firstInvalidStep(wizard.form, wizard.ctx) : 0))
const subtitle = computed(() => wizard.ctx?.lead?.lead_name || props.name)
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

// ---- step <-> URL ---------------------------------------------------------
// The current step lives in ?step= so the browser back button walks the steps.

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
    nextTick(() => document.querySelector('[aria-invalid="true"]')?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
    return
  }
  goTo(stepIndex.value + 1)
}

function back() {
  // If the previous history entry is the previous step, really go back so the
  // history doesn't grow; otherwise (deep link, refresh) step back in place.
  const previous = window.history.state?.back
  const previousStep = previous ? new URL(previous, window.location.origin).searchParams.get('step') : null
  if (previousStep === String(stepIndex.value)) router.back()
  else goTo(stepIndex.value - 1, { replace: true })
}

// ---- matches for edited "create new" values --------------------------------

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
    /* matches are a hint only; keep the previous ones */
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
  },
)

// ---- draft (IndexedDB, keyed by lead) --------------------------------------

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

// Don't lose the last keystrokes when the tab is hidden, reloaded or closed. The
// IndexedDB write is async and can be cut off during unload, so also write a
// synchronous localStorage copy (loadDraft picks the newest).
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
  if (minutes < 1) return 'a moment ago'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

// ---- submit ------------------------------------------------------------------

async function submit() {
  if (submitting.value || !online.value) return

  // re-check every step; jump to the first one that has a problem
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
    const deal = await api('pranera_crm.api.convert', toPayload(wizard.form, props.name))
    finished = true
    persist.cancel()
    await clearDraft(user, props.name)
    // full page navigation: /crm is a different app; keep the spinner until it loads
    window.location.assign(dealHref(deal))
  } catch (err) {
    if (err?.exc_type === 'LeadAlreadyConverted') {
      // converted meanwhile (double tap, another tab): show where the deal went
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
    errorBox.value?.$el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
}

onMounted(load)
watch(() => props.name, () => {
  finished = false
  load()
})
</script>
