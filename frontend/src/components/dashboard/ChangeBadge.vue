<template>
	<span class="inline-flex items-center gap-1 text-sm">
		<span
			v-if="change.pct !== null || change.kg"
			class="inline-flex items-center gap-0.5 font-medium"
			:class="change.kg >= 0 ? 'text-ink-green-6' : 'text-ink-red-8'"
		>
			<span
				:class="change.kg >= 0 ? 'lucide-arrow-up' : 'lucide-arrow-down'"
				class="size-3.5"
				aria-hidden="true"
			/>
			{{ formatKgs(Math.abs(change.kg), { short: true }) }}
			<template v-if="change.pct !== null"
				>({{ formatNumber(Math.abs(change.pct), { precision: 1 }) }}%)</template
			>
		</span>
		<span v-else class="text-ink-gray-5">{{ __('No change') }}</span>
		<span class="text-ink-gray-5">{{ label }}</span>
	</span>
</template>

<script setup>
import { formatKgs } from '@/lib/dashboard'
import { formatNumber } from '@/lib/format'
import { __ } from '@/translation'

defineProps({
	// { kg, pct }
	change: { type: Object, required: true },
	label: { type: String, required: true },
})
</script>
