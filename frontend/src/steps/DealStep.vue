<template>
  <div class="space-y-4">
    <h2 class="text-center text-xl font-semibold text-ink-gray-9">Deal details</h2>

    <p v-if="!hasFields" class="text-sm text-ink-gray-5">No extra details are required. Continue to review.</p>

    <template v-for="tab in tabs" :key="tab.name">
      <section v-for="section in tab.sections" :key="section.name" class="space-y-4">
        <h3 v-if="section.label && !section.hideLabel" class="text-base font-medium text-ink-gray-8">
          {{ section.label }}
        </h3>
        <div class="grid grid-cols-1 gap-4" :class="section.columns.length > 1 ? 'sm:grid-cols-2' : ''">
          <template v-for="(column, i) in section.columns" :key="column.name || i">
            <FieldControl
              v-for="field in column.fields"
              :key="field.fieldname"
              v-model="form.deal[field.fieldname]"
              :field="field"
              :statuses="ctx.deal_statuses"
              :error="showErrors ? errors[field.fieldname] : ''"
            />
          </template>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, toRef } from 'vue'
import FieldControl from '@/components/FieldControl.vue'
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
</script>
