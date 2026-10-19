import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import WorkbenchView from './views/WorkbenchView.vue'
import './styles/main.css'

const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', redirect: '/chat' },
  { path: '/chat/:id?', component: WorkbenchView },
  { path: '/:pathMatch(.*)*', redirect: '/chat' },
] })
createApp(App).use(createPinia()).use(router).mount('#app')
