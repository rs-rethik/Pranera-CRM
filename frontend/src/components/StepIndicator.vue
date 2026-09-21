<template>
  <nav aria-label="Progress">
    <!-- phone: compact bar -->
    <div class="sm:hidden">
      <div class="flex items-baseline justify-between text-sm">
        <span class="font-medium text-ink-gray-9">Step {{ current + 1 }} of {{ steps.length }}</span>
        <span class="text-ink-gray-6">{{ steps[current].label }}</span>
      </div>
      <div
        class="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-gray-3"
        role="progressbar"
        :aria-valuenow="current + 1"
        aria-valuemin="1"
        :aria-valuemax="steps.length"
      >
        <div
          class="h-full rounded-full bg-surface-gray-9 transition-all duration-300"
          :style="{ width: `${((current + 1) / steps.length) * 100}%` }"
        />
      </div>
    </div>

    <!-- tablet / desktop: numbered stepper -->
    <ol class="hidden items-center sm:flex">
      <li
        v-for="(step, i) in steps"
        :key="step.key"
        class="flex items-center"
        :class="i < steps.length - 1 ? 'flex-1' : ''"
      >
        <button
          type="button"
          class="group flex items-center gap-2 rounded-md py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
          :disabled="i > reachable || i === current"
          :aria-current="i === current ? 'step' : undefined"
          @click="emit('select', i)"
        >
          <span
            class="flex size-7 shrink-0 items-center justify-center rounded-full border text-sm font-medium"
            :class="
              i < current
                ? 'border-transparent bg-surface-gray-9 text-ink-white'
                : i === current
                  ? 'border-outline-gray-5 bg-surface-white text-ink-gray-9'
                  : 'border-outline-gray-2 bg-surface-white text-ink-gray-4'
            "
          >
            <span v-if="i < current" class="lucide-check size-4" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span
            class="text-sm"
            :class="i === current ? 'font-medium text-ink-gray-9' : 'text-ink-gray-5'"
          >
            {{ step.label }}
          </span>
        </button>
        <span v-if="i < steps.length - 1" class="mx-3 h-px flex-1 bg-outline-gray-2" aria-hidden="true" />
      </li>
    </ol>
  </nav>
</template>

<script setup>
defineProps({
  steps: { type: Array, required: true },
  current: { type: Number, required: true },
  // highest step index the user may jump to
  reachable: { type: Number, required: true },
})
const emit = defineEmits(['select'])
</script>
