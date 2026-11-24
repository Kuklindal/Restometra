<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { api, type Restaurant } from './api'

const restaurants = ref<Restaurant[]>([])
const selectedId = ref<number>()
const restaurant = computed(() => restaurants.value.find(item => item.id === selectedId.value))
const error = ref('')
const loading = ref(true)
const route = useRoute()
const nav = [
  { name: 'dashboard', label: 'Обзор', icon: '▦' },
  { name: 'day', label: 'Отчёт за день', icon: '▣' },
  { name: 'table', label: 'Аналитика столиков', icon: '⊞' },
  { name: 'reports', label: 'Отчёты и экспорт', icon: '▤' },
  { name: 'settings', label: 'Настройки ресторана', icon: '⚙' },
]

async function loadRestaurants() {
  error.value = ''
  loading.value = true
  try {
    restaurants.value = await api<Restaurant[]>('/restaurants')
    selectedId.value = restaurants.value.find(item => item.id === selectedId.value)?.id ?? restaurants.value[0]?.id
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(loadRestaurants)

function updateRestaurant(name: string, timezone: string) {
  if (restaurant.value) Object.assign(restaurant.value, { name, timezone })
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>Restometra<small>Аналитика ресторана</small></span>
      </RouterLink>
      <div class="workspace-label">Рабочее пространство</div>
      <nav aria-label="Навигация">
        <RouterLink
          v-for="link in nav"
          :key="link.name"
          :to="{ name: link.name }"
          :class="{ 'nav-active': route.name === link.name || (link.name === 'table' && route.name === 'table-day') }"
        >
          <span class="nav-icon" aria-hidden="true">{{ link.icon }}</span>{{ link.label }}
        </RouterLink>
      </nav>
      <div v-if="restaurant" class="location">
        <div class="location-badge" aria-hidden="true">{{ restaurant.name.charAt(0) }}</div>
        <div v-if="restaurants.length === 1"><strong>{{ restaurant.name }}</strong><small>{{ restaurant.timezone }}</small></div>
        <label v-else class="sr-only" for="restaurant">Ресторан</label>
        <select v-if="restaurants.length > 1" id="restaurant" v-model="selectedId">
          <option v-for="item in restaurants" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </div>
    </aside>
    <div class="main-area">
      <header class="topbar">
        <span>{{ route.name === 'table-day' ? 'Столик за день' : nav.find(link => link.name === route.name)?.label }}</span>
        <span v-if="restaurant?.is_demo" class="demo-badge"><i aria-hidden="true"></i>Демонстрационные данные</span>
      </header>
      <main>
        <div v-if="loading" class="panel state" role="status">Загружаем ресторан…</div>
        <div v-else-if="error" class="panel state" role="alert">
          <p>{{ error }}</p><button class="button" @click="loadRestaurants">Повторить</button>
        </div>
        <div v-else-if="!restaurant" class="panel state">В базе пока нет ресторанов. Для знакомства с панелью загрузите демонстрационные данные.</div>
        <RouterView v-else v-slot="{ Component }">
          <component :is="Component" :restaurant="restaurant"
            v-on="route.name === 'settings' ? { 'restaurant-updated': updateRestaurant } : {}" />
        </RouterView>
      </main>
    </div>
  </div>
</template>
