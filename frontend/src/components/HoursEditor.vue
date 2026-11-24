<script setup lang="ts">
import type { DayHours } from '../api'

const props = defineProps<{ hours: DayHours; label: string }>()
const emit = defineEmits<{ 'update:hours': [hours: DayHours] }>()
const defaultInterval = () => ({ opens: '12:00', closes: '22:00' })

function changeMode(event: Event) {
  const mode = (event.target as HTMLSelectElement).value as DayHours['mode']
  emit('update:hours', { mode, intervals: mode === 'intervals' ? [defaultInterval()] : [] })
}

function edit(index: number, endpoint: 'opens' | 'closes', event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('update:hours', {
    ...props.hours,
    intervals: props.hours.intervals.map((interval, i) => i === index ? { ...interval, [endpoint]: value } : interval),
  })
}
</script>

<template>
  <div class="hours-editor">
    <select :value="hours.mode" :aria-label="'Режим · ' + label" @change="changeMode">
      <option value="closed">Выходной</option>
      <option value="intervals">Рабочий день</option>
      <option value="all_day">Круглосуточно</option>
    </select>
    <div v-if="hours.mode === 'intervals'" class="slots">
      <div v-for="(interval, index) in hours.intervals" :key="index" class="interval-row">
        <input :value="interval.opens" type="time" required :aria-label="'Открытие · ' + label + ' · ' + (index + 1)" @input="edit(index, 'opens', $event)" />
        <span aria-hidden="true">—</span>
        <input :value="interval.closes" type="time" required :aria-label="'Закрытие · ' + label + ' · ' + (index + 1)" @input="edit(index, 'closes', $event)" />
        <span v-if="interval.closes && interval.opens && interval.closes < interval.opens" class="next-day">+1 день</span>
        <button v-if="hours.intervals.length > 1" type="button" class="button icon-button" :aria-label="'Удалить интервал ' + (index + 1)"
          @click="emit('update:hours', { ...hours, intervals: hours.intervals.filter((_, i) => i !== index) })">×</button>
      </div>
      <button v-if="hours.intervals.length < 24" type="button" class="text-link" @click="emit('update:hours', { ...hours, intervals: [...hours.intervals, defaultInterval()] })">+ Добавить интервал</button>
    </div>
    <span v-else class="muted">{{ hours.mode === 'all_day' ? 'От полуночи до следующей полуночи' : 'Рабочих интервалов нет' }}</span>
  </div>
</template>
