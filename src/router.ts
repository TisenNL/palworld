import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/map' },
    {
      path: '/lists',
      name: 'lists',
      component: () => import('@/views/ListsView.vue'),
    },
    {
      path: '/map',
      name: 'map',
      component: () => import('@/views/MapView.vue'),
    },
    {
      path: '/cakes',
      name: 'cakes',
      component: () => import('@/views/CakesView.vue'),
    },
    {
      path: '/breeding',
      name: 'breed',
      component: () => import('@/views/BreedingView.vue'),
    },
    {
      path: '/base-boost',
      name: 'base-boost',
      component: () => import('@/views/BaseBoostView.vue'),
    },
    { path: '/:pathMatch(.*)*', redirect: '/map' },
  ],
})
