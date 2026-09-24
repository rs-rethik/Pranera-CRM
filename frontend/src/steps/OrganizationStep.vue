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
            <span class="font-medium text-ink-gray-9">{{ candidate.organization_name }}</span>
            <span class="text-ink-gray-5">
              — {{ candidate.exact ? __('Exact match with the lead') : __("Matches the lead's {0}", [matchReason(candidate.reason)]) }}
            </span>
          </span>
        </template>
      </CandidateList>

      <Link
        v-model="org.existing"
        doctype="CRM Organization"
        :label="candidates.organizations?.length ? __('Or search for another organization') : __('Organization')"
        :placeholder="__('Search organization')"
        :description="matchNote"
        required
        :error="showErrors ? errors.existing : ''"
      />
    </template>

    <template v-if="!useExisting">
      <template v-if="customerTypeGateActive">
        <QuestionField
          v-model="customer.answers[customerTypeGateQuestion.question_key]"
          :question="customerTypeGateQuestion"
          :error="showErrors ? errors['cq_' + customerTypeGateQuestion.question_key] : ''"
        />
      </template>

      <template v-if="customerTypeUnlocked && gstGateActive && !ctx.customer.existing_customer">
        <QuestionField
          v-model="customer.answers[gstGateQuestion.question_key]"
          :question="gstGateQuestion"
          :error="showErrors ? errors['cq_' + gstGateQuestion.question_key] : ''"
        />

        <template v-if="gstAnswer === 'yes'">
          <div class="flex items-end gap-2">
            <FieldControl
              v-model="customer.address.values.gstin"
              :field="{ ...gstinField, description: __('Fetches the registered name and address.') }"
              class="flex-1"
              :error="showErrors ? errors.customer_gstin : ''"
            />
            <Button variant="subtle" :loading="fetchingGstin" :disabled="!canFetchGstin" @click="fetchFromGstin">
              {{ __('Fetch') }}
            </Button>
          </div>
          <ErrorMessage v-if="gstinLookupError" :message="gstinLookupError" />

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
            :field="orgNameLocked && field.fieldname === 'organization' ? { ...field, description: __('Auto-filled from the GSTIN above.') } : field"
            :disabled="orgNameLocked && field.fieldname === 'organization'"
            :class="field.fieldname === 'organization' || field.fieldname === 'website' ? 'col-span-2' : ''"
            :error="showErrors ? errors[field.fieldname] : ''"
          />
        </div>

        <div v-if="bridgeIndependentOrgQuestions.length" class="grid grid-cols-2 gap-x-4 gap-y-4">
          <QuestionField
            v-for="q in bridgeIndependentOrgQuestions"
            :key="q.question_key"
            v-model="customer.answers[q.question_key]"
            :question="q"
            :error="showErrors ? errors['cq_' + q.question_key] : ''"
          />
        </div>

        <p v-if="isIndividual" class="text-sm text-ink-gray-5">
          {{ __('No organization will be created — the customer will be named after the contact.') }}
        </p>
        <p v-else-if="candidates.auto_organization" class="text-sm text-ink-gray-5">
          {{ __('"{0}" already exists, so CRM will link it instead of creating a new organization.', [candidates.auto_organization]) }}
        </p>
        <p v-else class="text-sm text-ink-gray-5">
          {{ __('A new organization is created from these details. Leave the name empty to convert without one.') }}
        </p>

        <template v-if="ctx.customer?.enabled">
          <div class="h-px bg-outline-gray-2" />

          <Switch v-model="customer.enabled" :label="__('Set up this customer in ERPNext')" />

          <template v-if="customer.enabled">
            <p v-if="ctx.customer.existing_customer" class="text-sm text-ink-gray-5">
              {{ __('Already linked to Customer {0}.', [ctx.customer.existing_customer]) }}
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

              <h3 class="text-base font-medium text-ink-gray-8">{{ __('Address') }}</h3>

              <Switch v-if="!addressLocked" v-model="addressUseExisting" :label="__('Choose Existing')" />

              <Link
                v-if="addressUseExisting && !addressLocked"
                v-model="customer.address.existing"
                doctype="Address"
                :label="__('Address')"
                :placeholder="__('Search address')"
                required
                :error="showErrors ? errors.customer_existing_address : ''"
              />

              <template v-else>
                <div v-if="gstinField && !gstGateActive" class="flex items-end gap-2">
                  <FieldControl
                    v-model="customer.address.values.gstin"
                    :field="{ ...gstinField, description: __('Required unless GST Category is Unregistered or Overseas.') }"
                    class="flex-1"
                    :error="showErrors ? errors.customer_gstin : ''"
                  />
                  <Button variant="subtle" :loading="fetchingGstin" :disabled="!canFetchGstin" @click="fetchFromGstin">
                    {{ __('Fetch') }}
                  </Button>
                </div>

                <div class="grid grid-cols-2 gap-x-4 gap-y-4">
                  <FieldControl
                    v-for="field in otherAddressFields"
                    :key="field.fieldname"
                    v-model="customer.address.values[field.fieldname]"
                    :field="addressLocked ? { ...field, description: __('Auto-filled from the GSTIN above.') } : field"
                    :disabled="addressLocked"
                    :class="['address_line1', 'address_line2'].includes(field.fieldname) ? 'col-span-2' : ''"
                    :error="showErrors ? errors['customer_' + field.fieldname] : ''"
                  />
                </div>
                <p v-if="!addressLocked" class="text-sm text-ink-gray-5">
                  {{ __('Optional — leave the address blank to skip it.') }}
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
import { Button, ErrorMessage, Switch } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import CandidateList from '@/components/CandidateList.vue'
import FieldControl from '@/components/FieldControl.vue'
import QuestionField from '@/components/QuestionField.vue'
import { useDynamicOptionsRefresh } from '@/composables/useDynamicOptionsRefresh'
import { api, errorMessage } from '@/lib/api'
import { matchReason } from '@/lib/layout'
import { descendantKeys, visibleQuestions } from '@/lib/questions'
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
      org.existing = candidates.value.auto_organization || candidates.value.organizations?.[0]?.name || ''
    }
  },
})

const addressUseExisting = computed({
  get: () => customer.address.mode === 'existing',
  set: (on) => {
    customer.address.mode = on ? 'existing' : 'new'
  },
})

const matchNote = computed(() => {
  const match = (candidates.value.organizations || []).find((o) => o.name === org.existing)
  return match ? (match.exact ? __('Exact match with the lead') : __("Matches the lead's {0}", [matchReason(match.reason)])) : ''
})

const organizationQuestions = computed(() =>
  visibleQuestions(ctx.customer?.organization_questions, customer.answers),
)

useDynamicOptionsRefresh(
  'Organization',
  computed(() => ctx.customer?.organization_questions),
  customer.answers,
  computed(() => !!ctx.customer?.enabled),
)

const INDIVIDUAL_GATE_KEY = 'customer_type'
const INDIVIDUAL_OPTION_VALUE = 'individual'

const customerTypeGateQuestion = computed(() =>
  (ctx.customer?.organization_questions || []).find((q) => q.question_key === INDIVIDUAL_GATE_KEY),
)
const customerTypeAnswer = computed(() => customer.answers[INDIVIDUAL_GATE_KEY])
const customerTypeGateActive = computed(() => !!customerTypeGateQuestion.value)
const customerTypeUnlocked = computed(() => !customerTypeGateActive.value || customerTypeAnswer.value != null)
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
  (ctx.customer?.organization_questions || []).find((q) => q.question_key === GST_GATE_KEY),
)
const gstAnswer = computed(() => customer.answers[GST_GATE_KEY])
const gstGateActive = computed(() => !!gstGateQuestion.value)

const gstChildKeys = computed(() =>
  gstGateActive.value ? descendantKeys(ctx.customer?.organization_questions, GST_GATE_KEY) : new Set(),
)
const gstChildQuestions = computed(() =>
  organizationQuestions.value.filter((q) => gstChildKeys.value.has(q.question_key)),
)

const orgDetailsUnlocked = computed(
  () => customerTypeUnlocked.value && (!gstGateActive.value || gstAnswer.value != null),
)

const orgNameLocked = computed(() => gstGateActive.value && gstAnswer.value === 'yes')
const addressLocked = computed(() => gstGateActive.value && gstAnswer.value === 'yes')

const GATE_KEYS = new Set([INDIVIDUAL_GATE_KEY, GST_GATE_KEY])

const bridgeIndependentOrgQuestions = computed(() =>
  organizationQuestions.value.filter(
    (q) => !q.requires_erpnext_bridge && !GATE_KEYS.has(q.question_key) && !gstChildKeys.value.has(q.question_key),
  ),
)
const remainingOrganizationQuestions = computed(() =>
  organizationQuestions.value.filter(
    (q) => q.requires_erpnext_bridge && !GATE_KEYS.has(q.question_key) && !gstChildKeys.value.has(q.question_key),
  ),
)

const gstinField = computed(() => ctx.customer?.address_fields?.find((f) => f.fieldname === 'gstin'))
const otherAddressFields = computed(() => (ctx.customer?.address_fields || []).filter((f) => f.fieldname !== 'gstin'))
const canFetchGstin = computed(() => (customer.address.values.gstin || '').trim().length === 15)

const fetchingGstin = ref(false)
const gstinLookupError = ref('')

async function fetchFromGstin() {
  if (fetchingGstin.value || !canFetchGstin.value) return
  fetchingGstin.value = true
  gstinLookupError.value = ''
  try {
    const info = await api('pranera_crm.erpnext_customer.lookup_gstin', {
      gstin: customer.address.values.gstin.trim(),
    })
    if (info.business_name && org.mode === 'new' && !org.values.organization && !isIndividual.value) {
      org.values.organization = info.business_name
    }
    for (const [field, value] of Object.entries(info.address || {})) {
      if (value && !customer.address.values[field]) customer.address.values[field] = value
    }
  } catch (err) {
    gstinLookupError.value = errorMessage(err)
  } finally {
    fetchingGstin.value = false
  }
}
</script>
