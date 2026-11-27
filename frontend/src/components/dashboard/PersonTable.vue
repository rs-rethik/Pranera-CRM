<template>
	<div>
		<table class="w-full text-left text-base">
			<thead class="sticky top-0 bg-surface-white text-sm text-ink-gray-5">
				<tr class="border-b border-outline-gray-1">
					<th class="py-2 pr-3 font-normal">{{ __('Sales Person') }}</th>
					<th
						v-for="column in columns"
						:key="column.key"
						class="w-16 py-2 pr-3 text-right font-normal last:pr-0 sm:w-28"
					>
						{{ column.label }}
					</th>
				</tr>
			</thead>
			<tbody>
				<tr
					v-for="row in rows"
					:key="row.sales_person || ''"
					class="border-b border-outline-gray-1"
				>
					<td class="max-w-0 truncate py-2 pr-3 text-ink-gray-8">
						{{ personLabel(row.sales_person) }}
					</td>
					<td
						v-for="column in columns"
						:key="column.key"
						class="py-1 pr-1 text-right tabular-nums text-ink-gray-8 last:pr-0"
					>
						<button
							type="button"
							class="rounded px-2 py-1 hover:bg-surface-gray-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
							:title="column.title?.(row[column.key])"
							@click="$emit('open', { row, column })"
						>
							{{ column.format ? column.format(row[column.key]) : row[column.key] }}
						</button>
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { personLabel } from '@/lib/dashboard'
import { __ } from '@/translation'

defineProps({
	rows: { type: Array, required: true },
	// [{ key, label, format?, title? }]
	columns: { type: Array, required: true },
})
defineEmits(['open'])
</script>
