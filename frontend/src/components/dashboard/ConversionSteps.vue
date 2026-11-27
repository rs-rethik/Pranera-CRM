<template>
	<ol class="flex flex-col gap-2">
		<li
			v-for="(step, index) in steps"
			:key="step.stage"
			class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1"
		>
			<span class="truncate text-base text-ink-gray-8">{{ step.stage }}</span>
			<span class="text-right text-sm tabular-nums text-ink-gray-6">
				<b class="font-medium text-ink-gray-9">{{ step.reached }}</b>
				<template v-if="index < steps.length - 1">
					· {{ step.next_rate === null ? '—' : `${Math.round(step.next_rate)}%` }}
					{{ __('move on') }}
				</template>
			</span>
			<div class="col-span-2 h-1.5 overflow-hidden rounded-full bg-surface-gray-2">
				<div
					class="h-full rounded-full transition-[width] duration-300"
					:style="{ width: `${width(step)}%`, background: COLORS.open }"
				/>
			</div>
		</li>
	</ol>
</template>

<script setup>
import { COLORS } from '@/lib/dashboardCharts'
import { __ } from '@/translation'

const props = defineProps({ steps: { type: Array, required: true } })

// each bar is the share of the deals that started the path
const width = (step) =>
	props.steps[0]?.reached ? (step.reached / props.steps[0].reached) * 100 : 0
</script>
