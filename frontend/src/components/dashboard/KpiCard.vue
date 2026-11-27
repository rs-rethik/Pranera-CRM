<template>
	<button
		type="button"
		class="flex min-h-[104px] flex-col gap-2 rounded-lg border border-outline-gray-1 bg-surface-white p-4 text-left transition-colors hover:border-outline-gray-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
		:title="tooltip"
		@click="$emit('open')"
	>
		<span class="text-sm text-ink-gray-6">{{ label }}</span>
		<template v-if="loading">
			<Skeleton class="h-7 w-28 rounded" />
			<Skeleton class="h-4 w-20 rounded" />
		</template>
		<template v-else>
			<span class="text-2xl font-semibold leading-7 text-ink-gray-9">{{ value }}</span>
			<span class="flex min-h-4 items-center gap-2 text-sm text-ink-gray-5">
				<span
					v-if="change !== null"
					class="flex items-center gap-0.5 font-medium"
					:class="good ? 'text-ink-green-6' : 'text-ink-red-8'"
				>
					<span
						:class="change >= 0 ? 'lucide-arrow-up' : 'lucide-arrow-down'"
						class="size-3.5"
						aria-hidden="true"
					/>
					{{ changeText }}
				</span>
				<span class="truncate">{{ hint }}</span>
			</span>
		</template>
	</button>
</template>

<script setup>
import { computed } from 'vue'
import { Skeleton } from 'frappe-ui'
import { formatNumber } from '@/lib/format'

const props = defineProps({
	label: { type: String, required: true },
	value: { type: String, default: '' },
	hint: { type: String, default: '' },
	tooltip: { type: String, default: '' },
	// change against the period before; null hides it
	change: { type: Number, default: null },
	changeSuffix: { type: String, default: '%' },
	lowerIsBetter: { type: Boolean, default: false },
	loading: { type: Boolean, default: false },
})
defineEmits(['open'])

const good = computed(() => props.change >= 0 !== props.lowerIsBetter)
const changeText = computed(
	() => formatNumber(Math.abs(props.change), { precision: 1 }) + props.changeSuffix
)
</script>
