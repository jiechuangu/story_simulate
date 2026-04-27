import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Process from '../views/MainView.vue'
import SimulationView from '../views/SimulationView.vue'
import SimulationRunView from '../views/SimulationRunView.vue'
import StoryView from '../views/StoryView.vue'
import InteractionView from '../views/InteractionView.vue'
import RoleControlView from '../views/RoleControlView.vue'
import RoleIntroView from '../views/RoleIntroView.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true
  },
  {
    path: '/story/:storyId',
    name: 'Story',
    component: StoryView,
    props: true
  },
  {
    path: '/interaction/:storyId',
    name: 'Interaction',
    component: InteractionView,
    props: true
  },
  {
    path: '/interaction/:storyId/role/:characterId',
    name: 'RoleControl',
    component: RoleControlView,
    props: true
  },
  {
    path: '/interaction/:storyId/role/:characterId/intro',
    name: 'RoleIntro',
    component: RoleIntroView,
    props: true
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
