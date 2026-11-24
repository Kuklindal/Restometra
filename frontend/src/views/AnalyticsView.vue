<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, apiRoot, restaurantPath, type Metrics, type Report, type Restaurant, type Table } from '../api'
import VisitList from '../components/VisitList.vue'
import { at, dateLabel, duration, localToday, number, shiftDay, statusLabels } from '../format'

const props = defineProps<{ restaurant: Restaurant }>()
const Chart = defineAsyncComponent(() => import('../components/Chart.vue'))
const route = useRoute()
const headings: Record<string, [string, string]> = {
  dashboard: ['Обзор обслуживания', 'Посещаемость, скорость работы зала и качество данных за выбранный период.'],
  day: ['Отчёт за день', 'График операционного дня, показатели и события обслуживания.'],
  table: ['Аналитика столиков', 'Динамика обслуживания и история посещений выбранного столика.'],
  'table-day': ['Столик за день', 'Хронология визитов, источники событий и статусы подтверждения.'],
  reports: ['Отчёты и экспорт', 'Сформируйте отчёт по готовым дневным данным и выгрузите таблицу CSV.'],
}
const mode = computed(() => String(route.name))
const heading = computed(() => headings[mode.value] ?? headings.dashboard)
const oneDay = computed(() => ['day', 'table-day'].includes(mode.value) || (mode.value === 'reports' && period.value === 'day'))
const tableView = computed(() => ['table', 'table-day'].includes(mode.value))
const period = ref('month')
const periodDate = ref('')
const start = ref('')
const end = ref('')
const tableId = ref<number | ''>('')
const tables = ref<Table[]>([])
const report = ref<Report>()
const error = ref('')
const notice = ref('')
const busy = ref(false)
const queuing = ref(false)
let request = 0
const base = computed(() => restaurantPath(props.restaurant.id))

function preset() {
  if (mode.value !== 'reports') {
    if (oneDay.value) start.value = end.value
    else if (mode.value === 'table') start.value = end.value.slice(0, 7) + '-01'
    return
  }
  if (period.value === 'custom' || !periodDate.value) return
  if (period.value === 'day') {
    start.value = end.value = periodDate.value
  } else if (period.value === 'week') {
    const weekday = new Date(periodDate.value + 'T00:00:00Z').getUTCDay()
    start.value = shiftDay(periodDate.value, -((weekday + 6) % 7))
    end.value = shiftDay(start.value, 6)
  } else {
    start.value = periodDate.value + '-01'
    const next = new Date(start.value + 'T00:00:00Z')
    next.setUTCMonth(next.getUTCMonth() + 1)
    end.value = shiftDay(next.toISOString().slice(0, 10), -1)
  }
}

async function load() {
  const id = ++request
  busy.value = false
  error.value = ''
  report.value = undefined
  if (!start.value || !end.value || (!oneDay.value && start.value > end.value)) {
    error.value = 'Укажите корректные даты начала и окончания.'
    return
  }
  if (tableView.value && tableId.value === '') return
  busy.value = true
  const query = new URLSearchParams({ start: oneDay.value ? end.value : start.value, end: end.value })
  if (tableId.value !== '') query.set('table_id', String(tableId.value))
  try {
    const data = await api<Report>(base.value + '/reports?' + query)
    if (id === request) report.value = data
  } catch (cause) {
    if (id === request) error.value = (cause as Error).message
  } finally {
    if (id === request) busy.value = false
  }
}
watch([() => props.restaurant.id, () => route.fullPath], async () => {
  const id = ++request
  error.value = ''
  notice.value = ''
  report.value = undefined
  tables.value = []
  tableId.value = ''
  const anchor = props.restaurant.latest_day ?? shiftDay(localToday(props.restaurant.timezone), -1)
  end.value = typeof route.query.day === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(route.query.day) && Number.isFinite(Date.parse(route.query.day))
    ? route.query.day : anchor
  period.value = mode.value === 'dashboard' ? 'custom' : 'month'
  periodDate.value = end.value.slice(0, 7)
  start.value = mode.value === 'dashboard' ? shiftDay(end.value, -29) : end.value
  preset()
  busy.value = true
  try {
    if (tableView.value || mode.value === 'reports') {
      const choices = await api<Table[]>(base.value + '/tables')
      if (id !== request) return
      tables.value = choices
      if (tableView.value) {
        const linked = choices.find(item => item.id === Number(route.query.table))
        tableId.value = linked?.id ?? choices[0]?.id ?? ''
      }
    }
    if (mode.value !== 'reports') await load()
  } catch (cause) {
    if (id === request) error.value = (cause as Error).message
  } finally {
    if (id === request) busy.value = false
  }
}, { immediate: true })

const total = computed(() => report.value?.metrics)
const day = computed(() => report.value?.days.length === 1 ? report.value.days[0] : undefined)
const processed = computed(() => report.value?.days.filter(item => item.status === 'PROCESSED').length ?? 0)
const closed = computed(() => report.value?.days.filter(item => item.status === 'CLOSED').length ?? 0)
const selectedTable = computed(() => tables.value.find(item => item.id === tableId.value)?.name)

function changePeriod() {
  const anchor = props.restaurant.latest_day ?? shiftDay(localToday(props.restaurant.timezone), -1)
  periodDate.value = period.value === 'month' ? anchor.slice(0, 7) : anchor
  preset()
}

function csv(kind: string) {
  const result = report.value
  if (!result) return ''
  const query = new URLSearchParams({ start: result.start, end: result.end, kind })
  if (result.table_id !== null) query.set('table_id', String(result.table_id))
  return apiRoot + base.value + '/reports.csv?' + query
}

async function reprocess() {
  if (!day.value) return
  queuing.value = true
  notice.value = ''
  try {
    await api(base.value + '/processing/' + day.value.day, { method: 'POST' })
    notice.value = 'Дата поставлена в очередь на обработку. Обновите отчёт, чтобы проверить статус.'
    await load()
  } catch (cause) {
    notice.value = (cause as Error).message
  } finally {
    queuing.value = false
  }
}

const tiles = computed(() => {
  const data = total.value
  if (!data) return []
  return [
    { title: 'Завершённые визиты', value: number(data.completed_visits), note: number(data.started_visits) + ' начато', icon: '▥', hue: 'violet' },
    { title: 'Средняя длительность', value: duration(data.average_duration_seconds), note: 'Медиана · ' + duration(data.median_duration_seconds), icon: '◷', hue: 'blue' },
    { title: 'Первый контакт', value: duration(data.average_first_contact_seconds), note: number(data.contact_samples) + ' наблюдений', icon: '◴', hue: 'orange' },
    { title: 'Контакты официанта', value: number(data.counts.WAITER_CONTACT), note: number(data.late_first_contacts) + ' первых контактов свыше 5 мин', icon: '▧', hue: 'green' },
  ]
})

function chartOptions(labels: string[], values: (number | null)[], type: 'line' | 'bar', unit = '') {
  return {
    animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (value: number | null) => value == null ? '—' : number(value) + unit },
    grid: { left: 40, right: 20, top: 20, bottom: 32 },
    xAxis: { type: 'category', data: labels, boundaryGap: type === 'bar',
      axisLabel: { color: '#53637d', hideOverlap: true }, axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e5e9f2' } } },
    yAxis: { type: 'value', axisLabel: { color: '#53637d' }, splitLine: { lineStyle: { color: '#edf0f6' } } },
    series: [{
      type, data: values, smooth: true, symbolSize: 7, barMaxWidth: 22,
      itemStyle: { color: type === 'line' ? '#5145d7' : '#7265e8', borderRadius: [4, 4, 0, 0] },
      lineStyle: { width: 3 },
      ...(type === 'line' ? { areaStyle: { color: '#e3e0fb', opacity: 0.55 } } : {}),
    }],
  }
}
const visitTrend = computed(() => chartOptions(
  report.value?.days.map(item => dateLabel(item.day)) ?? [],
  report.value?.days.map(item => item.metrics?.completed_visits ?? null) ?? [], 'line',
))
const contactTrend = computed(() => chartOptions(
  report.value?.days.map(item => dateLabel(item.day)) ?? [],
  report.value?.days.map(item => item.metrics?.average_first_contact_seconds == null ? null
    : Math.round(item.metrics.average_first_contact_seconds / 6) / 10) ?? [], 'line', ' мин',
))
const hourly = computed(() => chartOptions(
  Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0') + ':00'), total.value?.hours ?? [], 'bar',
))
const serviceRows: [string, (data: Metrics) => number][] = [
  ['Подачи блюд', data => data.counts.FOOD_SERVED],
  ['Подачи напитков', data => data.counts.DRINK_SERVED],
  ['Принесение счёта', data => data.counts.BILL_PRESENTED],
  ['Визиты дольше 2 часов', data => data.long_visits],
]
</script>

<template>
  <section class="page-heading">
    <div><h1>{{ heading[0] }}</h1><p>{{ heading[1] }}</p></div>
    <div v-if="report" class="period-chip">▣ <span>{{ dateLabel(report.start, true) }}<template v-if="report.start !== report.end"> — {{ dateLabel(report.end, true) }}</template></span></div>
  </section>

  <form class="panel filter-bar" @submit.prevent="notice = ''; load()">
    <label v-if="mode === 'reports'">
      Период
      <select v-model="period" aria-label="Период" @change="changePeriod">
        <option value="day">День</option><option value="week">Неделя</option>
        <option value="month">Месяц</option><option value="custom">Произвольный период</option>
      </select>
    </label>
    <label v-if="tableView || mode === 'reports'">
      Столик
      <select v-model="tableId" aria-label="Столик" :disabled="!tables.length">
        <option v-if="!tableView" value="">Все столики</option>
        <option v-for="table in tables" :key="table.id" :value="table.id">{{ table.name }}</option>
      </select>
    </label>
    <label v-if="mode === 'reports' && period !== 'custom'">
      {{ period === 'month' ? 'Месяц' : period === 'week' ? 'Дата в неделе' : 'Операционная дата' }}
      <input :key="period" v-model="periodDate" :type="period === 'month' ? 'month' : 'date'" required @input="preset" />
    </label>
    <template v-else>
      <label v-if="!oneDay">Начало периода <input v-model="start" type="date" required :max="end || undefined" /></label>
      <label>{{ oneDay ? 'Операционная дата' : 'Конец периода' }} <input v-model="end" type="date" required /></label>
    </template>
    <button class="button primary" :disabled="busy || (tableView && tableId === '')">{{ mode === 'reports' ? 'Сформировать отчёт' : 'Показать' }}</button>
    <RouterLink v-if="mode === 'table' && tableId !== ''" class="button" :to="{ name: 'table-day', query: { table: tableId, day: end } }">Столик за день</RouterLink>
    <RouterLink v-if="mode === 'table-day' && tableId !== ''" class="button" :to="{ name: 'table', query: { table: tableId, day: end } }">Столик за период</RouterLink>
  </form>

  <p v-if="notice" class="notice neutral" role="status">{{ notice }}</p>
  <div v-if="busy" class="panel state" role="status">Загружаем отчёт…</div>
  <div v-else-if="error" class="notice error" role="alert">{{ error }}</div>
  <div v-else-if="tableView && !tables.length" class="panel state">Для ресторана ещё не добавлены столики.</div>
  <div v-else-if="!report" class="panel state">Выберите период и сформируйте отчёт.</div>

  <template v-else>
    <section v-if="day && oneDay" class="panel day-info">
      <div class="section-title">
        <div>
          <h2>{{ dateLabel(day.day, true) }}<template v-if="tableView && selectedTable"> · {{ selectedTable }}</template></h2>
          <p>{{ day.schedule.timezone }}<template v-if="day.schedule.is_override"> · Исключение из графика</template></p>
        </div>
        <span class="status" :class="day.status.toLowerCase()">{{ statusLabels[day.status] }}</span>
      </div>
      <p v-if="!day.schedule.windows.length">Ресторан закрыт по графику.</p>
      <ul v-else class="windows">
        <li v-for="window in day.schedule.windows" :key="window.opens_at">
          <strong>{{ at(window.opens_at, day.schedule.timezone, true) }} — {{ at(window.closes_at, day.schedule.timezone, true) }}</strong>
          <small>Наблюдение до {{ at(window.observed_until, day.schedule.timezone, true) }}</small>
        </li>
      </ul>
      <p v-if="day.schedule.ready_at" class="muted">Расчёт доступен с {{ at(day.schedule.ready_at, day.schedule.timezone, true) }} при наличии исходных данных.</p>
      <p v-if="day.run_status === 'PENDING'">В очереди на обработку.</p>
      <p v-if="day.run_status === 'RUNNING'">Выполняется расчёт.</p>
      <p v-if="day.error" class="error-text">{{ day.error }}</p>
      <button v-if="mode === 'day' && day.day >= restaurant.tracking_since && (day.status !== 'CLOSED' || day.historical)" class="button"
        :disabled="queuing || day.run_status === 'RUNNING' || day.run_status === 'PENDING'" @click="reprocess">
        {{ day.historical ? 'Пересчитать день' : 'Запустить обработку' }}
      </button>
    </section>

    <section class="notice" :class="report.missing_days.length ? 'warning' : 'neutral'">
      <span class="notice-icon" aria-hidden="true">{{ report.missing_days.length ? '!' : '✓' }}</span>
      <div>
        <strong>{{ report.missing_days.length ? 'Данные за период неполные' : 'Полнота данных' }}</strong>
        <p>{{ processed }} обработано · {{ closed }} выходных<template v-if="report.missing_days.length"> · {{ report.missing_days.length }} без готовой статистики</template></p>
        <details v-if="report.missing_days.length">
          <summary>Показать пропущенные дни</summary>
          <ul><li v-for="item in report.missing_days" :key="item.day">{{ dateLabel(item.day, true) }} · {{ statusLabels[item.status] }}</li></ul>
        </details>
      </div>
    </section>

    <div v-if="total" class="metrics-grid">
      <article v-for="metric in tiles" :key="metric.title" class="panel metric">
        <span class="metric-icon" :class="metric.hue" aria-hidden="true">{{ metric.icon }}</span>
        <h2>{{ metric.title }}</h2><strong>{{ metric.value }}</strong><small>{{ metric.note }}</small>
      </article>
    </div>
    <div v-else class="panel state">{{ day?.status === 'CLOSED' ? 'За выходной статистика не формируется.' : 'Готовых показателей за выбранный период пока нет.' }}</div>

    <div v-if="total && mode !== 'reports'" class="charts-grid">
      <article v-if="!oneDay" class="panel">
        <div class="section-title"><div><h2>Динамика посещений</h2><p>Завершённые визиты по операционным дням</p></div><span class="chart-key">Посещения</span></div>
        <Chart :options="visitTrend" label="Число завершённых визитов по дням" />
      </article>
      <article class="panel">
        <div class="section-title"><div><h2>Распределение по часам</h2><p>Время начала визитов по местному времени</p></div></div>
        <Chart :options="hourly" label="Начало визитов по часам" />
      </article>
      <article v-if="mode === 'table'" class="panel">
        <div class="section-title"><div><h2>Время первого контакта</h2><p>Среднее ожидание официанта по дням, в минутах</p></div></div>
        <Chart :options="contactTrend" label="Среднее время ожидания официанта по дням" />
      </article>
      <article class="panel">
        <h2>События обслуживания</h2>
        <dl class="service-list">
          <div v-for="[label, value] in serviceRows" :key="label"><dt>{{ label }}</dt><dd>{{ number(value(total)) }}</dd></div>
          <div><dt>Медиана до первого контакта</dt><dd>{{ duration(total.median_first_contact_seconds) }}</dd></div>
        </dl>
      </article>
    </div>

    <section v-if="report.tables.length && ['dashboard', 'day', 'reports'].includes(mode)" class="panel">
      <div class="section-title">
        <div><h2>Статистика столиков</h2><p>Загрузка и время обслуживания по столикам</p></div>
        <a v-if="mode === 'reports'" class="button" :href="csv('tables')">CSV по столикам</a>
      </div>
      <div class="table-scroll"><table>
        <thead><tr><th>Столик</th><th>Визиты</th><th>Средняя длительность</th><th>Первый контакт</th></tr></thead>
        <tbody>
          <tr v-for="row in report.tables" :key="row.id">
            <td><RouterLink class="text-link" :to="{ name: mode === 'day' ? 'table-day' : 'table', query: { table: row.id, day: report.end } }">{{ row.name }}</RouterLink></td>
            <td>{{ number(row.metrics.completed_visits) }}</td><td>{{ duration(row.metrics.average_duration_seconds) }}</td><td>{{ duration(row.metrics.average_first_contact_seconds) }}</td>
          </tr>
        </tbody>
      </table></div>
    </section>

    <section v-if="mode === 'reports' || (!oneDay && tableView && total)" class="panel">
      <div class="section-title">
        <div><h2>Показатели по дням</h2><p>{{ dateLabel(report.start, true) }} — {{ dateLabel(report.end, true) }}</p></div>
        <a v-if="mode === 'reports'" class="button primary" :href="csv('days')">Скачать CSV</a>
      </div>
      <div class="table-scroll"><table>
        <thead><tr><th>Операционный день</th><th>Статус</th><th>Визиты</th><th>Средняя длительность</th><th>Первый контакт</th></tr></thead>
        <tbody>
          <tr v-for="item in report.days" :key="item.day">
            <td><RouterLink class="text-link" :to="{ name: tableView ? 'table-day' : 'day', query: { day: item.day, ...(tableView ? { table: tableId } : {}) } }">{{ dateLabel(item.day, true) }}</RouterLink></td>
            <td><span class="status" :class="item.status.toLowerCase()">{{ statusLabels[item.status] }}</span></td>
            <td>{{ item.metrics?.completed_visits ?? '—' }}</td><td>{{ duration(item.metrics?.average_duration_seconds) }}</td><td>{{ duration(item.metrics?.average_first_contact_seconds) }}</td>
          </tr>
        </tbody>
      </table></div>
    </section>

    <VisitList v-if="total && (mode === 'day' || tableView)" :visits="report.visits" />
  </template>
</template>
