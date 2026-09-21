<template>
  <ul class="space-y-2" role="radiogroup" :aria-label="label">
    <li v-for="item in items" :key="item.name">
      <button
        type="button"
        role="radio"
        :aria-checked="modelValue === item.name"
        class="flex min-h-14 w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :class="
          modelValue === item.name
            ? 'border-outline-gray-5 bg-surface-gray-2'
            : 'border-outline-gray-2 bg-surface-white hover:bg-surface-gray-1'
        "
        @click="emit('update:modelValue', item.name)"
      >
        <span
          class="flex size-5 shrink-0 items-center justify-center rounded-full border"
          :class="modelValue === item.name ? 'border-transparent bg-surface-gray-9 text-ink-white' : 'border-outline-gray-3'"
        >
          <span v-if="modelValue === item.name" class="lucide-check size-3.5" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate text-base font-medium text-ink-gray-9">{{ item.title }}</span>
          <span v-if="item.subtitle" class="block truncate text-sm text-ink-gray-5">{{ item.subtitle }}</span>
        </span>
        <span
          v-if="item.badge"
          class="shrink-0 rounded-full bg-surface-gray-3 px-2 py-0.5 text-xs text-ink-gray-7"
        >
          {{ item.badge }}
        </span>
      </button>
    </li>
  </ul>
</template>

<script setup>
defineProps({
  // [{ name, title, subtitle?, badge? }]
  items: { type: Array, required: true },
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
</script>
