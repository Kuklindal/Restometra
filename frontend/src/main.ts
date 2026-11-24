import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import AnalyticsView from './views/AnalyticsView.vue'
import SettingsView from './views/SettingsView.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: AnalyticsView },
    { path: '/day', name: 'day', component: AnalyticsView },
    { path: '/tables', name: 'table', component: AnalyticsView },
    { path: '/tables/day', name: 'table-day', component: AnalyticsView },
    { path: '/reports', name: 'reports', component: AnalyticsView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
createApp(App).use(router).mount('#app')
