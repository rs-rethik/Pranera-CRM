<template>
  <div class="space-y-4">
    <h2 class="text-center text-xl font-semibold text-ink-gray-9">{{ __('Contact') }}</h2>

    <Switch v-model="useExisting" :label="__('Choose Existing')" />

    <Link
      v-if="useExisting"
      v-model="contact.existing"
      doctype="Contact"
      :label="__('Contact')"
      :placeholder="__('Search contact')"
      :description="matchNote"
      required
      :error="showErrors ? errors.existing : ''"
    />

    <template v-else>
      <div class="grid grid-cols-2 gap-x-4 gap-y-4">
        <FieldControl
          v-for="field in fields"
          :key="field.fieldname"
          v-model="contact.values[field.fieldname]"
          :field="{ ...field, reqd: field.fieldname === 'first_name' ? 1 : field.reqd }"
          :class="FULL_WIDTH.includes(field.fieldname) ? 'col-span-2' : ''"
          :error="showErrors ? errors[field.fieldname] : ''"
        />
      </div>
      <p v-if="candidates.auto_contact" class="text-sm text-ink-gray-5">
        {{ __('Contact {0} already has this email or phone, so CRM will link it instead of creating a new contact.', [candidates.auto_contact]) }}
      </p>
      <p v-else class="text-sm text-ink-gray-5">{{ __('A new contact is created from these details.') }}</p>
    </template>

    <template v-if="ctx.customer?.enabled && customer.enabled && contactQuestions.length">
      <div class="h-px bg-outline-gray-2" />
      <div class="grid grid-cols-2 gap-x-4 gap-y-4">
        <QuestionField
          v-for="q in contactQuestions"
          :key="q.question_key"
          v-model="customer.contactAnswers[q.question_key]"
          :question="q"
          :error="showErrors ? errors['cq_' + q.question_key] : ''"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, toRef } from 'vue'
import { Switch } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import FieldControl from '@/components/FieldControl.vue'
import QuestionField from '@/components/QuestionField.vue'
import { matchReason } from '@/lib/layout'
import { visibleQuestions } from '@/lib/questions'
import { __ } from '@/translation'

const w = inject('wizard')
const { ctx, form } = w
const candidates = toRef(w, 'candidates')
const errors = toRef(w, 'errors')
const showErrors = toRef(w, 'showErrors')
const contact = form.contact
const customer = form.customer

// display order: pairs share a row, these span the full width
const ORDER = ['salutation', 'gender', 'first_name', 'last_name', 'email', 'phone', 'mobile_no', 'job_title']
const FULL_WIDTH = ['email', 'job_title']
const fields = computed(() =>
  [...ctx.contact_fields].sort((a, b) => ORDER.indexOf(a.fieldname) - ORDER.indexOf(b.fieldname)),
)

const useExisting = computed({
  get: () => contact.mode === 'existing',
  set: (on) => {
    contact.mode = on ? 'existing' : 'new'
    if (on && !contact.existing) {
      contact.existing = candidates.value.auto_contact || candidates.value.contacts?.[0]?.name || ''
    }
  },
})

const matchNote = computed(() => {
  const match = (candidates.value.contacts || []).find((c) => c.name === contact.existing)
  return match ? __("Matches the lead's {0}", [matchReason(match.reason)]) : ''
})

const contactQuestions = computed(() => visibleQuestions(ctx.customer?.contact_questions, customer.contactAnswers))
</script>
