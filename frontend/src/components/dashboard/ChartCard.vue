<template>
	<section class="flex flex-col rounded-lg border border-outline-gray-1 bg-surface-white">
		<header class="flex items-baseline justify-between gap-3 px-4 pt-4">
			<h2 class="text-base font-medium text-ink-gray-8">{{ title }}</h2>
			<span v-if="subtitle" class="truncate text-sm text-ink-gray-5">{{ subtitle }}</span>
		</header>
		<!-- one fixed height for loading, empty and filled, so the page never jumps; a table
		     (`fit`) grows with its rows instead -->
		<div
			class="p-4"
			:class="fit && !loading && !empty ? 'max-h-[420px] overflow-auto' : 'h-[280px]'"
		>
			<Skeleton v-if="loading" class="h-full w-full rounded" />
			<div
				v-else-if="empty"
				class="flex h-full flex-col items-center justify-center gap-1 text-center"
			>
				<span class="lucide-chart-column size-6 text-ink-gray-4" aria-hidden="true" />
				<p class="max-w-xs text-sm text-ink-gray-5">{{ emptyText }}</p>
			</div>
			<slot v-else />
		</div>
	</section>
</template>

<script setup>
import { Skeleton } from 'frappe-ui'

defineProps({
	title: { type: String, required: true },
	subtitle: { type: String, default: '' },
	loading: { type: Boolean, default: false },
	empty: { type: Boolean, default: false },
	emptyText: { type: String, default: '' },
	fit: { type: Boolean, default: false },
})
</script>
