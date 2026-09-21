<template>
  <div class="space-y-6">
    <StepHeading
      title="Deal details"
      description="These are the fields your CRM requires when creating a deal."
    />

    <p v-if="!hasFields" class="rounded-lg bg-surface-gray-2 p-4 text-sm text-ink-gray-6">
      No extra details are required for a deal. Continue to review.
    </p>

    <template v-for="tab in tabs" :key="tab.name">
      <section v-for="section in tab.sections" :key="section.name" class="space-y-4">
        <h3 v-if="section.label && !section.hideLabel" class="text-base font-medium text-ink-gray-8">
          {{ section.label }}
        </h3>
        <div class="grid gap-4" :class="columnsClass(section)">
          <div v-for="(column, i) in section.columns" :key="column.name || i" class="space-y-4">
            <FieldControl
              v-for="field in column.fields"
              :key="field.fieldname"
              v-model="form.deal[field.fieldname]"
              :field="field"
              :statuses="ctx.deal_statuses"
              :error="showErrors ? errors[field.fieldname] : ''"
            />
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, toRef } from 'vue'
import FieldControl from '@/components/FieldControl.vue'
import StepHeading from '@/components/StepHeading.vue'
import { visibleSections } from '@/lib/layout'

const w = inject('wizard')
const { ctx, form } = w
const errors = toRef(w, 'errors')
const showErrors = toRef(w, 'showErrors')

// Rendered straight from CRM's "Required Fields" layout for CRM Deal.
const tabs = computed(() =>
  (ctx.deal_layout || [])
    .map((tab) => ({ ...tab, sections: visibleSections(tab) }))
    .filter((tab) => tab.sections.length),
)
const hasFields = computed(() => tabs.value.length > 0)

function columnsClass(section) {
  // one column on phones; CRM's column count from tablet up
  return { 1: '', 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-2 lg:grid-cols-3' }[Math.min(section.columns.length, 3)]
}
</script>
