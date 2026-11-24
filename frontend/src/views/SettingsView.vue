<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, restaurantPath, type Restaurant, type Settings } from '../api'
import HoursEditor from '../components/HoursEditor.vue'
import { validateSettings } from '../settingsValidation'

const props = defineProps<{ restaurant: Restaurant }>()
const emit = defineEmits<{ 'restaurant-updated': [name: string, timezone: string] }>()
const config = ref<Settings>()
const error = ref('')
const notice = ref('')
const busy = ref(false)
const saving = ref(false)
const touched = ref(false)
const errors = computed(() => config.value ? validateSettings(config.value) : [])
const days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
const endpoint = computed(() => restaurantPath(props.restaurant.id) + '/settings')
let request = 0

async function load() {
  const id = ++request
  config.value = undefined
  touched.value = false
  notice.value = ''
  error.value = ''
  busy.value = true
  try {
    const saved = await api<Settings>(endpoint.value)
    if (id === request) config.value = saved
  } catch (cause) {
    if (id === request) error.value = (cause as Error).message
  } finally {
    if (id === request) busy.value = false
  }
}
watch(() => props.restaurant.id, load, { immediate: true })

async function save() {
  touched.value = true
  notice.value = ''
  error.value = ''
  if (!config.value || errors.value.length) return
  const id = request
  saving.value = true
  try {
    const saved = await api<Settings>(endpoint.value, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config.value),
    })
    if (id !== request) return
    config.value = saved
    notice.value = 'Настройки сохранены.'
    touched.value = false
    emit('restaurant-updated', saved.name, saved.timezone)
  } catch (cause) {
    if (id === request) error.value = (cause as Error).message
  } finally {
    saving.value = false
  }
}

function addOverride() {
  touched.value = true
  config.value?.overrides.push({ day: '', hours: { mode: 'closed', intervals: [] } })
}
</script>

<template>
  <section class="page-heading"><div>
    <h1>Настройки ресторана</h1><p>Управляйте рабочими часами, исключениями и параметрами ежедневной обработки.</p>
  </div></section>
  <div v-if="busy" class="panel state" role="status">Загружаем настройки…</div>
  <div v-else-if="!config" class="panel state" role="alert"><p>{{ error }}</p><button class="button" @click="load">Повторить</button></div>
  <form v-else class="settings" novalidate @change="touched = true; notice = ''" @submit.prevent="save">
    <fieldset :disabled="saving">
      <section class="panel">
        <h2>Основные параметры</h2>
        <div class="form-grid">
          <label>Название ресторана <input v-model.trim="config.name" maxlength="120" required /></label>
          <label>Часовой пояс IANA <input v-model.trim="config.timezone" placeholder="Asia/Krasnoyarsk" maxlength="80" required /></label>
        </div>
      </section>

      <section class="panel">
        <h2>График работы</h2><p class="muted">Если время закрытия раньше времени открытия, смена заканчивается на следующий день.</p>
        <div class="schedule-list">
          <div v-for="(hours, index) in config.weekly_hours" :key="days[index]" class="schedule-row">
            <strong>{{ days[index] }}</strong>
            <HoursEditor :hours="hours" :label="days[index]" @update:hours="config.weekly_hours[index] = $event; touched = true; notice = ''" />
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="section-title">
          <div><h2>Исключения из расписания</h2><p>График на выбранную дату имеет приоритет над недельным.</p></div>
          <button v-if="config.overrides.length < 400" type="button" class="button" @click="addOverride">+ Добавить дату</button>
        </div>
        <p v-if="!config.overrides.length" class="muted">Исключений пока нет.</p>
        <div v-else class="schedule-list">
          <div v-for="(item, index) in config.overrides" :key="index" class="schedule-row exception-row">
            <input v-model="item.day" type="date" required :aria-label="'Дата исключения ' + (index + 1)" />
            <HoursEditor v-model:hours="item.hours" :label="item.day || 'Исключение ' + (index + 1)" @update:hours="touched = true; notice = ''" />
            <button type="button" class="button icon-button" :aria-label="'Удалить исключение ' + (index + 1)" @click="config.overrides.splice(index, 1); notice = ''">×</button>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2>Запас наблюдения и запуск обработки</h2>
        <div class="form-grid">
          <label>Наблюдение после закрытия, мин <input v-model.number="config.observation_minutes" type="number" min="0" max="1440" required /><small>Учитывается до начала следующего рабочего интервала.</small></label>
          <label>Задержка начала обработки, мин <input v-model.number="config.processing_delay_minutes" type="number" min="0" max="1440" required /><small>Отсчитывается от окончания наблюдения за операционным днём.</small></label>
        </div>
      </section>

      <div v-if="touched && errors.length" class="notice error" role="alert">
        <div><strong>Проверьте настройки</strong><ul><li v-for="message in errors" :key="message">{{ message }}</li></ul></div>
      </div>
      <div v-if="error" class="notice error" role="alert">{{ error }}</div>
      <div v-if="notice" class="notice neutral" role="status">{{ notice }}</div>
      <button class="button primary">{{ saving ? 'Сохраняем…' : 'Сохранить настройки' }}</button>
    </fieldset>
  </form>
</template>
