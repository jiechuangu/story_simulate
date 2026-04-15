<template>
  <section class="report-history">
    <div class="header">
      <span class="title">Recent Reports</span>
      <span class="meta">{{ reports.length }} items</span>
    </div>
    <div v-if="loading" class="empty">Loading...</div>
    <div v-else-if="reports.length === 0" class="empty">No reports yet.</div>
    <div v-else class="list">
      <button
        v-for="report in reports"
        :key="report.report_id"
        class="item"
        @click="openReport(report.report_id)"
      >
        <div class="row">
          <span class="id">{{ report.report_id }}</span>
          <span class="status" :class="report.status">{{ report.status }}</span>
        </div>
        <div class="name">{{ report.outline?.title || 'Untitled Report' }}</div>
        <div class="desc">{{ truncate(report.simulation_requirement || '-', 80) }}</div>
        <div class="meta-row">
          <span>{{ report.simulation_id || '--' }}</span>
          <span>{{ formatDate(report.created_at) }}</span>
        </div>
      </button>
    </div>
  </section>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listReports } from '../api/report'

const router = useRouter()
const reports = ref([])
const loading = ref(true)
let timer = null

const loadReports = async () => {
  try {
    loading.value = true
    const res = await listReports(12)
    if (res.success) {
      reports.value = res.data || []
    }
  } finally {
    loading.value = false
  }
}

const openReport = (reportId) => {
  router.push({ name: 'Report', params: { reportId } })
}

const truncate = (text, max) => text.length > max ? `${text.slice(0, max)}...` : text
const formatDate = (value) => value ? new Date(value).toLocaleString() : '--'

onMounted(() => {
  loadReports()
  timer = setInterval(loadReports, 8000)
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
