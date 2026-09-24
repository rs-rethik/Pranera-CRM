<template>
  <div class="space-y-4">
    <h2 class="text-center text-xl font-semibold text-ink-gray-9">{{ __('Contact') }}</h2>

    <Switch v-model="useExisting" :label="__('Choose Existing')" />

    <template v-if="useExisting">
      <CandidateList
        v-if="candidates.contacts?.length"
        :candidates="candidates.contacts"
        :selected="contact.existing"
        @select="(name) => (contact.existing = name)"
      >
        <template #default="{ candidate }">
          <span class="min-w-0">
            <span class="font-medium text-ink-gray-9">{{ contactLabel(candidate) }}</span>
            <span class="text-ink-gray-5"> — {{ __("Matches the lead's {0}", [matchReason(candidate.reason)]) }}</span>
          </span>
        </template>
      </CandidateList>

      <Link
        v-model="contact.existing"
        doctype="Contact"
        :label="candidates.contacts?.length ? __('Or search for someone else') : __('Contact')"
        :placeholder="__('Search contact')"
        :description="matchNote"
        required
        :error="showErrors ? errors.existing : ''"
      />
    </template>

    <template v-else>
      <div v-if="bridgeIndependentContactQuestions.length" class="grid grid-cols-2 gap-x-4 gap-y-4">
        <QuestionField
          v-for="q in bridgeIndependentContactQuestions"
          :key="q.question_key"
          v-model="customer.contactAnswers[q.question_key]"
          :question="q"
          :error="showErrors ? errors['cq_' + q.question_key] : ''"
        />
      </div>

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
      <div v-if="verified" class="flex items-center gap-2 text-sm text-ink-green-3">
        <span>{{ __('Email verified') }}</span>
      </div>
      <div v-else-if="canVerify" class="space-y-2">
        <div class="flex items-end gap-2">
          <Button variant="subtle" :loading="verification.sending" @click="send">
            {{ codeSent ? __('Resend code') : __('Verify Email') }}
          </Button>
          <template v-if="codeSent">
            <FormControl
              v-model="verification.code"
              type="text"
              size="sm"
              inputmode="numeric"
              maxlength="6"
              :placeholder="__('Enter the code')"
              class="flex-1"
              @keyup.enter="confirm"
            />
            <Button variant="solid" :loading="verification.confirming" :disabled="!verification.code.trim()" @click="confirm">
              {{ __('Confirm') }}
            </Button>
          </template>
        </div>
        <p v-if="codeSent" class="text-sm text-ink-gray-5">
          {{ __('A code was sent to {0}. Ask the customer for it.', [contact.values.email]) }}
        </p>
        <ErrorMessage :message="verification.error" />
      </div>
      <p v-if="candidates.auto_contact" class="text-sm text-ink-gray-5">
        {{ __('Contact {0} already has this email or phone, so CRM will link it instead of creating a new contact.', [candidates.auto_contact]) }}
      </p>
      <p v-else class="text-sm text-ink-gray-5">{{ __('A new contact is created from these details.') }}</p>
    </template>

    <template v-if="ctx.customer?.enabled && customer.enabled && bridgeContactQuestions.length">
      <div class="h-px bg-outline-gray-2" />
      <div class="grid grid-cols-2 gap-x-4 gap-y-4">
        <QuestionField
          v-for="q in bridgeContactQuestions"
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
import { Button, ErrorMessage, FormControl, Switch } from 'frappe-ui'
import { Link } from 'frappe-ui/frappe'
import CandidateList from '@/components/CandidateList.vue'
import FieldControl from '@/components/FieldControl.vue'
import QuestionField from '@/components/QuestionField.vue'
import { useDynamicOptionsRefresh } from '@/composables/useDynamicOptionsRefresh'
import { useEmailVerification } from '@/composables/useEmailVerification'
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
const { state: verification, verified, canVerify, codeSent, send, confirm } = useEmailVerification(
  ctx.lead.name,
  contact,
)

const ORDER = ['first_name', 'last_name', 'email', 'phone', 'mobile_no', 'job_title']
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

function contactLabel(c) {
  const name = [c.first_name, c.last_name].filter(Boolean).join(' ') || c.name
  const extra = c.email_id || c.mobile_no
  return extra ? `${name} (${extra})` : name
}

const contactQuestions = computed(() => visibleQuestions(ctx.customer?.contact_questions, customer.contactAnswers))

useDynamicOptionsRefresh(
  'Contact',
  computed(() => ctx.customer?.contact_questions),
  customer.contactAnswers,
  computed(() => !!ctx.customer?.enabled),
)

const bridgeIndependentContactQuestions = computed(() =>
  contactQuestions.value.filter((q) => !q.requires_erpnext_bridge),
)
const bridgeContactQuestions = computed(() => contactQuestions.value.filter((q) => q.requires_erpnext_bridge))
</script>
