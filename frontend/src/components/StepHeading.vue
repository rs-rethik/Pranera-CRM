<template>
  <div>
    <h2 class="text-xl font-semibold text-ink-gray-9">{{ title }}</h2>
    <p v-if="description" class="mt-1 text-sm text-ink-gray-5">{{ description }}</p>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
})
</script>
