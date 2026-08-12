import { createRouter, createWebHistory } from 'vue-router'
const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue')
  },
  {
    path: '/graph',
    name: 'Graph',
    component: () => import('../views/GraphPage.vue')
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/DashboardPage.vue')
  },
  {
    path: '/search',
    name: 'Search',
    component: () => import('../views/SearchPage.vue')
  },
  {
    path: '/path',
    name: 'Path',
    component: () => import('../views/PathPage.vue')
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('../views/KnowledgePage.vue')
  },
  {
    path: '/questions',
    name: 'Questions',
    component: () => import('../views/QuestionsPage.vue')
  },
  {
    path: '/mistakes',
    name: 'Mistakes',
    component: () => import('../views/MistakesPage.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
