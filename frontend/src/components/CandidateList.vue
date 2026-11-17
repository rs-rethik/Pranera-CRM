<template>
	<div class="space-y-2">
		<button
			v-for="c in candidates"
			:key="c.name"
			type="button"
			class="flex w-full items-center justify-between gap-3 rounded border px-3 py-2 text-left text-sm transition-colors"
			:class="
				c.name === selected
					? 'border-outline-gray-4 bg-surface-gray-2'
					: 'border-outline-gray-2 hover:bg-surface-gray-1'
			"
			@click="emit('select', c.name)"
		>
			<slot :candidate="c" />
			<span v-if="c.name === selected" class="shrink-0 text-ink-gray-6">{{
				__('Selected')
			}}</span>
		</button>
	</div>
</template>

<script setup>
import { __ } from '@/translation'

defineProps({
	candidates: { type: Array, required: true },
	selected: { type: String, default: '' },
})
const emit = defineEmits(['select'])
</script>
