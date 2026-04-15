<template>
  <section class="project-history">
    <div class="header">
      <span class="title">Recent Project Tasks</span>
      <span class="meta">{{ projects.length }} items</span>
    </div>
    <div v-if="loading" class="empty">Loading...</div>
    <div v-else-if="projects.length === 0" class="empty">No project tasks yet.</div>
    <div v-else class="list">
      <button
        v-for="project in projects"
        :key="project.project_id"
        class="item"
        @click="openProject(project.project_id)"
      >
        <div class="row">
          <span class="id">{{ project.project_id }}</span>
          <span class="status" :class="project.status">{{ project.status }}</span>
        </div>
        <div class="name">{{ project.name || 'Unnamed Project' }}</div>
        <div class="desc">{{ truncate(project.simulation_requirement || '-', 80) }}</div>
        <div class="meta-row">
          <span>chunk {{ project.chunk_size || '--' }}/{{ project.chunk_overlap || '--' }}</span>
          <span>{{ formatDate(project.updated_at) }}</span>
        </div>
      </button>
    </div>
  </section>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects } from '../api/graph'

const router = useRouter()
const projects = ref([])
const loading = ref(true)
let timer = null

const loadProjects = async () => {
  try {
    loading.value = true
    const res = await listProjects(12)
    if (res.success) {
      projects.value = res.data || []
    }
  } finally {
    loading.value = false
  }
}

const openProject = (projectId) => {
  router.push({ name: 'Process', params: { projectId } })
}

const truncate = (text, max) => text.length > max ? `${text.slice(0, max)}...` : text
const formatDate = (value) => value ? new Date(value).toLocaleString() : '--'

onMounted(() => {
  loadProjects()
  timer = setInterval(loadProjects, 8000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.project-history {
  margin-top: 28px;
  border: 1px solid #ececec;
  border-radius: 10px;
  padding: 18px;
  background: linear-gradient(180deg, #fff, #fafafa);
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.title {
  font-weight: 700;
  letter-spacing: 0.04em;
}
.meta, .empty {
  color: #777;
  font-size: 13px;
}
.list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.item {
  text-align: left;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  background: white;
  padding: 12px;
  cursor: pointer;
}
.item:hover {
  border-color: #111;
}
.row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}
.status {
  font-size: 11px;
  text-transform: uppercase;
  color: #666;
}
.status.ontology_generating,
.status.graph_building {
  color: #d9480f;
}
.status.graph_completed,
.status.ontology_generated {
  color: #2b8a3e;
}
.status.failed {
  color: #c92a2a;
}
.name {
  font-weight: 600;
  margin-bottom: 6px;
}
.desc {
  color: #666;
  font-size: 13px;
  line-height: 1.4;
}

.meta-row {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: #999;
  font-size: 12px;
}
</style>
