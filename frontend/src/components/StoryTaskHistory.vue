<template>
  <section class="report-history">
    <div class="header">
      <span class="title">Recent Story Sessions</span>
      <span class="meta">{{ sessions.length }} items</span>
    </div>
    <div v-if="loading" class="empty">Loading...</div>
    <div v-else-if="sessions.length === 0" class="empty">No story sessions yet.</div>
    <div v-else class="list">
      <button
        v-for="session in sessions"
        :key="session.report_id"
        class="item"
        @click="openStorySession(session.report_id)"
      >
        <div class="row">
          <span class="id">{{ session.report_id }}</span>
          <span class="status" :class="session.status">{{ session.status }}</span>
        </div>
        <div class="name">{{ session.title || session.outline?.title || 'Untitled Story' }}</div>
        <div class="desc">{{ truncate(session.simulation_requirement || session.premise || '-', 80) }}</div>
        <div class="meta-row">
          <span>{{ session.simulation_id || '--' }}</span>
          <span>{{ formatDate(session.created_at) }}</span>
        </div>
      </button>
    </div>
  </section>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listStorySessions } from '../api/story'

const router = useRouter()
const sessions = ref([])
const loading = ref(true)
let timer = null

const loadStorySessions = async () => {
  try {
    loading.value = true
    const res = await listStorySessions(12)
    if (res.success) {
      sessions.value = res.data || []
    }
  } finally {
    loading.value = false
  }
}

const openStorySession = (storyId) => {
  router.push({ name: 'Story', params: { storyId } })
}

const truncate = (text, max) => text.length > max ? `${text.slice(0, max)}...` : text
const formatDate = (value) => value ? new Date(value).toLocaleString() : '--'

onMounted(() => {
  loadStorySessions()
  timer = setInterval(loadStorySessions, 8000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.report-history {
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
.status.processing,
.status.planning,
.status.generating {
  color: #d9480f;
}
.status.completed {
  color: #2b8a3e;
}
.status.failed,
.status.error {
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
