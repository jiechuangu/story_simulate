import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import StoryView from '../views/StoryView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Home', component: Home },
    { path: '/story/:id', name: 'Story', component: StoryView, props: true }
  ]
})
