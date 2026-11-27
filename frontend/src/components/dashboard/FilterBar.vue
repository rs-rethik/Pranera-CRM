<template>
	<div class="flex flex-wrap items-center gap-2">
		<Select
			:model-value="filters.preset"
			:options="PRESETS"
			:aria-label="__('Period')"
			@update:model-value="setPreset"
		/>
		<DateRangePicker
			v-if="filters.preset === 'custom'"
			class="w-56"
			:model-value="[filters.from, filters.to]"
			:placeholder="__('From – to')"
			@update:model-value="setRange"
		/>
		<TabButtons
			:model-value="filters.granularity"
			:buttons="GRANULARITIES"
			@update:model-value="update({ granularity: $event })"
		/>
		<MultiSelect
			v-if="options.sales_persons.length > 1"
			class="w-52"
			:model-value="filters.persons"
			:options="options.sales_persons.map((name) => ({ label: name, value: name }))"
			:placeholder="options.sees_all ? __('All Sales Persons') : __('My team')"
			:aria-label="__('Sales Person')"
			@update:model-value="update({ persons: $event || [] })"
		/>
		<Select
			v-if="options.territories.length"
			:model-value="filters.territory"
			:options="[{ value: '', label: __('All territories') }, ...options.territories]"
			:aria-label="__('Territory')"
			@update:model-value="update({ territory: $event })"
		/>
		<Button v-if="changed" variant="ghost" :label="__('Reset')" @click="$emit('reset')" />
	</div>
</template>

<script setup>
import { computed } from 'vue'
import { Button, DateRangePicker, MultiSelect, Select, TabButtons } from 'frappe-ui'
import { DEFAULTS, GRANULARITIES, PRESETS, granularityFor, presetRange } from '@/lib/dashboard'

const props = defineProps({
	filters: { type: Object, required: true },
	options: { type: Object, required: true },
})
const emit = defineEmits(['change', 'reset'])

const changed = computed(
	() =>
		props.filters.preset !== DEFAULTS.preset ||
		props.filters.granularity !== granularityFor(props.filters.preset) ||
		props.filters.territory ||
		props.filters.persons.length
)

function update(patch) {
	emit('change', { ...props.filters, ...patch })
}

function setPreset(preset) {
	const granularity = granularityFor(preset)
	if (preset !== 'custom') return update({ preset, granularity, from: '', to: '' })
	// start the custom range from what is on screen
	update({ preset, granularity, ...presetRange(props.filters.preset) })
}

function setRange(range) {
	const [from, to] = range || []
	if (from && to) update({ from, to })
}
</script>
