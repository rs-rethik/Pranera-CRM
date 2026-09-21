<template>
  <nav class="mb-4 flex items-center justify-center gap-2" aria-label="Progress">
    <span class="sr-only">Step {{ current + 1 }} of {{ total }}</span>
    <span
      v-for="i in total"
      :key="i"
      class="flex size-3 items-center justify-center rounded-full"
      :class="i - 1 === current ? 'border border-outline-gray-5' : ''"
      :aria-current="i - 1 === current ? 'step' : undefined"
    >
      <span class="size-1.5 rounded-full" :class="i - 1 === current ? 'bg-surface-gray-9' : 'bg-surface-gray-3'" />
    </span>
  </nav>
</template>

<script setup>
defineProps({
  total: { type: Number, required: true },
  current: { type: Number, required: true },
})
</script>
