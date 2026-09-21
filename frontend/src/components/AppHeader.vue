<template>
  <header
    class="sticky top-0 z-20 border-b border-outline-gray-2 bg-surface-white pt-[env(safe-area-inset-top)]"
  >
    <div class="mx-auto flex h-14 w-full max-w-3xl items-center gap-3 px-4">
      <a
        :href="homeHref"
        class="flex min-w-0 items-center gap-2 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
        aria-label="Pranera CRM home"
      >
        <img
          src="/icons/icon-192.png"
          alt=""
          class="size-8 shrink-0 rounded-lg"
          width="32"
          height="32"
        />
        <span class="truncate text-lg font-semibold text-ink-gray-9">Pranera CRM</span>
      </a>
      <span v-if="subtitle" class="ml-1 hidden min-w-0 truncate text-sm text-ink-gray-5 sm:block">
        / {{ subtitle }}
      </span>
      <div class="ml-auto flex items-center gap-1">
        <a
          v-if="backHref"
          :href="backHref"
          class="inline-flex h-9 items-center gap-1 rounded-md px-2 text-sm text-ink-gray-6 hover:bg-surface-gray-2"
        >
          <span class="lucide-arrow-left size-4" />
          <span class="hidden sm:inline">{{ backLabel }}</span>
          <span class="sm:hidden">Back</span>
        </a>
      </div>
    </div>
    <p v-if="subtitle" class="mx-auto max-w-3xl truncate px-4 pb-2 text-sm text-ink-gray-5 sm:hidden">
      {{ subtitle }}
    </p>
  </header>
</template>

<script setup>
import { router } from '@/router'

defineProps({
  subtitle: { type: String, default: '' },
  backHref: { type: String, default: '' },
  backLabel: { type: String, default: 'Back to CRM' },
})

const homeHref = router.resolve({ name: 'Home' }).href
</script>
