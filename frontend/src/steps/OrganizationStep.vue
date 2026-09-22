<template>
  <div class="space-y-4">
    <h2 class="text-center text-xl font-semibold text-ink-gray-9">{{ __('Organization') }}</h2>

    <Switch v-model="useExisting" :label="__('Choose Existing')" />

    <Link
      v-if="useExisting"
      v-model="org.existing"
      doctype="CRM Organization"
      :label="__('Organization')"
      :placeholder="__('Search organization')"
      :description="matchNote"
      required
      :error="showErrors ? errors.existing : ''"
    />

    <template v-else>
      <div class="grid grid-cols-2 gap-x-4 gap-y-4">
        <FieldControl
          v-for="field in ctx.organization_fields"
          :key="field.fieldname"
          v-model="org.values[field.fieldname]"
          :field="field"
          :class="field.fieldname === 'organization' || field.fieldname === 'website' ? 'col-span-2' : ''"
          :error="showErrors ? errors[field.fieldname] : ''"
        />
      </div>
      <p v-if="candidates.auto_organization" class="text-sm text-ink-gray-5">
        {{ __('"{0}" already exists, so CRM will link it instead of creating a new organization.', [candidates.auto_organization]) }}
      </p>
      <p v-else class="text-sm text-ink-gray-5">
        {{ __('A new organization is created from these details. Leave the name empty to convert without one.') }}
      </p>
    </template>

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
              v-for="q in organizationQuestions"
              :key="q.question_key"
              v-model="customer.answers[q.question_key]"
              :question="q"
              :error="showErrors ? errors['cq_' + q.question_key] : ''"
            />
          </div>

          <h3 class="text-base font-medium text-ink-gray-8">{{ __('Address') }}</h3>

          <div v-if="gstinField" class="flex items-end gap-2">
            <FieldControl
              v-model="customer.address.gstin"
              :field="{ ...gstinField, description: __('Required unless GST Category is Unregistered or Overseas.') }"
              class="flex-1"
              :error="showErrors ? errors.customer_gstin : ''"
            />
            <Button variant="subtle" :loading="fetchingGstin" :disabled="!canFetchGstin" @click="fetchFromGstin">
              {{ __('Fetch') }}
            </Button>
          </div>
          <ErrorMessage v-if="gstinLookupError" :message="gstinLookupError" />

          <div class="grid grid-cols-2 gap-x-4 gap-y-4">
            <FieldControl
              v-for="field in otherAddressFields"
              :key="field.fieldname"
              v-model="customer.address[field.fieldname]"
              :field="field"
              :class="['address_line1', 'address_line2'].includes(field.fieldname) ? 'col-span-2' : ''"
              :error="showErrors ? errors['customer_' + field.fieldname] : ''"
            />
          </div>
          <p class="text-sm text-ink-gray-5">{{ __('Optional — leave the address blank to skip it.') }}</p>
        </template>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, ref, toRef } from 'vue'
import { Button, ErrorMessage, Switch } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import FieldControl from '@/components/FieldControl.vue'
import QuestionField from '@/components/QuestionField.vue'
import { api, errorMessage } from '@/lib/api'
import { matchReason } from '@/lib/layout'
import { visibleQuestions } from '@/lib/questions'
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
    // start from the best match so "Choose existing" is one tap
    if (on && !org.existing) {
      org.existing = candidates.value.auto_organization || candidates.value.organizations?.[0]?.name || ''
    }
  },
})

const matchNote = computed(() => {
  const match = (candidates.value.organizations || []).find((o) => o.name === org.existing)
  return match ? (match.exact ? __('Exact match with the lead') : __("Matches the lead's {0}", [matchReason(match.reason)])) : ''
})

const organizationQuestions = computed(() =>
  visibleQuestions(ctx.customer?.organization_questions, customer.answers),
)

// -- "Fetch" a GSTIN's registered business name and address, via India Compliance --

const gstinField = computed(() => ctx.customer?.address_fields?.find((f) => f.fieldname === 'gstin'))
const otherAddressFields = computed(() => (ctx.customer?.address_fields || []).filter((f) => f.fieldname !== 'gstin'))
const canFetchGstin = computed(() => (customer.address.gstin || '').trim().length === 15)

const fetchingGstin = ref(false)
const gstinLookupError = ref('')

async function fetchFromGstin() {
  if (fetchingGstin.value || !canFetchGstin.value) return
  fetchingGstin.value = true
  gstinLookupError.value = ''
  try {
    const info = await api('pranera_crm.erpnext_customer.lookup_gstin', {
      gstin: customer.address.gstin.trim(),
    })
    if (info.business_name && org.mode === 'new' && !org.values.organization) {
      org.values.organization = info.business_name
    }
    for (const [field, value] of Object.entries(info.address || {})) {
      if (value && !customer.address[field]) customer.address[field] = value
    }
  } catch (err) {
    gstinLookupError.value = errorMessage(err)
  } finally {
    fetchingGstin.value = false
  }
}
</script>
