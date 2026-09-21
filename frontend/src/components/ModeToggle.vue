<template>
  <div class="grid grid-cols-2 gap-1 rounded-lg bg-surface-gray-2 p-1" role="radiogroup" :aria-label="label">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      :aria-checked="modelValue === option.value"
      class="h-10 rounded-md px-3 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      :class="
        modelValue === option.value
          ? 'bg-surface-white text-ink-gray-9 shadow-sm'
          : 'text-ink-gray-5 hover:text-ink-gray-8'
      "
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, required: true },
  options: { type: Array, required: true },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
</script>
