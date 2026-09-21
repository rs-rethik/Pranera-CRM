<template>
  <div
    class="flex items-start gap-3 rounded-lg border p-3 text-sm"
    :class="tone === 'warning'
      ? 'border-outline-amber-1 bg-surface-amber-1 text-ink-amber-3'
      : tone === 'error'
        ? 'border-outline-red-1 bg-surface-red-1 text-ink-red-4'
        : 'border-outline-gray-2 bg-surface-gray-2 text-ink-gray-7'"
    :role="tone === 'error' ? 'alert' : 'status'"
  >
    <span :class="icon" class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
    <div class="min-w-0 flex-1"><slot /></div>
    <slot name="action" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tone: { type: String, default: 'info' }, // info | warning | error
})

const icon = computed(() =>
  props.tone === 'error' ? 'lucide-circle-alert' : props.tone === 'warning' ? 'lucide-triangle-alert' : 'lucide-info',
)
</script>
