<script setup lang="ts">
import type { Visit } from '../api'
import { at, dateLabel, duration, eventLabels, reviewLabels, sourceLabels } from '../format'

defineProps<{ visits: Visit[] }>()
</script>

<template>
  <section class="panel">
    <h2>Посещения и события</h2>
    <p v-if="!visits.length" class="muted">За выбранный период визитов нет.</p>
    <div v-else class="visits">
      <details v-for="visit in visits" :key="visit.id">
        <summary>
          <span><strong>{{ visit.table_name }}</strong><small>{{ dateLabel(visit.operating_date) }} · {{ at(visit.started_at, visit.timezone, true) }}</small></span>
          <span><small>Длительность</small>{{ visit.duration_seconds === null ? 'Не завершён' : duration(visit.duration_seconds) }}</span>
          <span><small>Первый контакт</small>{{ duration(visit.first_contact_seconds) }}</span>
          <span class="chevron" aria-hidden="true"></span>
        </summary>
        <ol v-if="visit.events.length" class="timeline">
          <li v-for="event in visit.events" :key="event.id">
            <time :datetime="event.occurred_at">{{ at(event.occurred_at, visit.timezone, true) }}</time>
            <span>
              <strong>{{ eventLabels[event.type] ?? event.type }}</strong>
              <small>{{ sourceLabels[event.source] ?? event.source }} · {{ reviewLabels[event.review_status] ?? event.review_status }}
                <template v-if="event.confidence !== null"> · {{ Math.round(event.confidence * 100) }}%</template>
              </small>
            </span>
          </li>
        </ol>
        <p v-else class="muted">По визиту нет сохранённых событий.</p>
      </details>
    </div>
  </section>
</template>
