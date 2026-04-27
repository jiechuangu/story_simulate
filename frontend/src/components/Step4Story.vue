<template>
  <div class="story-panel">
    <section class="story-header">
      <div>
        <div class="eyebrow">Step 4</div>
        <h1>{{ storyTitle }}</h1>
        <p class="premise">{{ storyPremise }}</p>
      </div>
      <div class="header-actions">
        <span class="status-pill" :class="statusClass">{{ statusLabel }}</span>
        <button class="ghost-btn" :disabled="retrying || !props.simulationId" @click="restartStory">
          {{ retrying ? 'Regenerating...' : 'Restart Story' }}
        </button>
      </div>
    </section>

    <section v-if="latestChapter" class="chapter-shell">
      <div class="chapter-meta">
        <span>Chapter {{ latestChapter.chapter_no }}</span>
        <span>{{ latestChapter.title }}</span>
      </div>
      <article class="chapter-card">
        <h2>{{ latestChapter.title }}</h2>
        <p class="chapter-summary">{{ latestChapter.summary }}</p>
        <div class="chapter-content" v-html="renderChapter(latestChapter.content)"></div>
      </article>
    </section>

    <section v-else class="chapter-card placeholder">
      <div class="spinner"></div>
      <p>Generating the current chapter...</p>
    </section>

    <section class="topic-shell">
      <div class="topic-header">
        <div>
          <div class="eyebrow">Next Chapter</div>
          <h3>Choose the next topic</h3>
        </div>
        <button v-if="canGoToInteraction" class="primary-btn" @click="goToInteraction">Go to Step 5</button>
      </div>

      <div v-if="isGenerating" class="topic-loading">
        <div class="spinner small"></div>
        <span>Generating next chapter options...</span>
      </div>

      <div v-else-if="topics.length === 0" class="topic-loading">
        <span>No topic candidates yet.</span>
      </div>

      <div v-else class="topic-grid">
        <button
          v-for="topic in topics"
          :key="topic.topic_id"
          class="topic-card"
          :disabled="selecting || isGenerating"
          @click="pickTopic(topic)"
        >
          <div class="topic-top">
            <span class="topic-type">{{ topic.tension_type || 'story' }}</span>
            <span class="topic-promise">{{ topic.promise || 'Continue the arc' }}</span>
          </div>
          <h4>{{ topic.title }}</h4>
          <p>{{ topic.summary }}</p>
          <div v-if="topic.focus_characters?.length" class="topic-characters">
            {{ topic.focus_characters.join(' / ') }}
          </div>
        </button>
      </div>
    </section>

    <section class="timeline-shell">
      <div class="topic-header">
        <div>
          <div class="eyebrow">Progress</div>
          <h3>Chapter Timeline</h3>
        </div>
      </div>
      <div v-if="chapters.length === 0" class="timeline-empty">No chapters yet.</div>
      <div v-else class="timeline-list">
        <div v-for="chapter in chapters" :key="chapter.chapter_no" class="timeline-item">
          <div class="timeline-no">{{ String(chapter.chapter_no).padStart(2, '0') }}</div>
          <div class="timeline-body">
            <div class="timeline-title">{{ chapter.title }}</div>
            <div class="timeline-summary">{{ chapter.summary }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createStorySession, getStorySession, selectNextTopic } from '../api/story'

const router = useRouter()

const props = defineProps({
  storyId: String,
  simulationId: String,
  systemLogs: Array
})

const emit = defineEmits(['add-log', 'update-status'])

const storySession = ref(null)
const selecting = ref(false)
const retrying = ref(false)
let pollTimer = null

const log = (msg) => emit('add-log', msg)

const statusClass = computed(() => {
  if (!storySession.value) return 'processing'
  if (storySession.value.status === 'failed') return 'error'
  if (storySession.value.status === 'generating' || storySession.value.status === 'pending') return 'processing'
  return 'ready'
})

const statusLabel = computed(() => {
  if (!storySession.value) return 'Loading'
  if (storySession.value.status === 'failed') return 'Error'
  if (storySession.value.status === 'generating' || storySession.value.status === 'pending') return 'Generating'
  return 'Waiting for Choice'
})

const isGenerating = computed(() => {
  if (!storySession.value) return true
  return storySession.value.status === 'generating' || storySession.value.status === 'pending'
})

const storyTitle = computed(() => storySession.value?.title || 'Interactive Story')
const storyPremise = computed(() => storySession.value?.premise || storySession.value?.simulation_requirement || 'Generating story premise...')
const chapters = computed(() => storySession.value?.chapters || [])
const latestChapter = computed(() => {
  const list = chapters.value
  return list.length ? list[list.length - 1] : null
})
const topics = computed(() => storySession.value?.topic_candidates || [])
const canGoToInteraction = computed(() => !!props.storyId && !!latestChapter.value)

const renderChapter = (text) => {
  if (!text) return ''
  return text
    .split(/\n{2,}/)
    .map((block) => `<p>${block.replace(/\n/g, '<br>')}</p>`)
    .join('')
}

const refreshStorySession = async () => {
  if (!props.storyId) return
  try {
    const res = await getStorySession(props.storyId)
    storySession.value = res.data
    if (storySession.value.status === 'failed') {
      emit('update-status', 'error')
      stopPolling()
    } else if (storySession.value.status === 'waiting_for_choice') {
      emit('update-status', 'completed')
      stopPolling()
    } else {
      emit('update-status', 'processing')
      startPolling()
    }
  } catch (err) {
    log(`Load story session failed: ${err.message}`)
    emit('update-status', 'error')
  }
}

const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(refreshStorySession, 2500)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const pickTopic = async (topic) => {
  if (!props.storyId || selecting.value) return
  selecting.value = true
  emit('update-status', 'processing')
  try {
    log(`Selected next topic: ${topic.title}`)
    await selectNextTopic(props.storyId, topic.topic_id)
    if (storySession.value) {
      storySession.value.status = 'generating'
      storySession.value.topic_candidates = []
    }
    startPolling()
    await refreshStorySession()
  } catch (err) {
    log(`Choose topic failed: ${err.message}`)
    emit('update-status', 'error')
  } finally {
    selecting.value = false
  }
}

const restartStory = async () => {
  if (retrying.value || !props.simulationId) return
  retrying.value = true
  try {
    log(`Restarting story for simulation: ${props.simulationId}`)
    const res = await createStorySession({
      simulation_id: props.simulationId,
      force_regenerate: true
    })
    const nextReportId = res.data?.report_id
    if (!nextReportId) {
      throw new Error('Failed to create a new story session')
    }
    stopPolling()
    router.replace({ name: 'Story', params: { storyId: nextReportId } })
  } catch (err) {
    log(`Restart story failed: ${err.message}`)
  } finally {
    retrying.value = false
  }
}

const goToInteraction = () => {
  if (!props.storyId) return
  router.push({ name: 'Interaction', params: { storyId: props.storyId } })
}

watch(() => props.storyId, async (newId) => {
  stopPolling()
  storySession.value = null
  if (newId) {
    await refreshStorySession()
  }
}, { immediate: true })

onMounted(() => {
  if (props.storyId) {
    log(`Story workspace initialized: ${props.storyId}`)
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.story-panel {
  height: 100%;
  overflow: auto;
  padding: 24px;
  background: linear-gradient(180deg, #f2ede3 0%, #f8f4ec 100%);
  color: #221f1b;
}
.story-header,
.chapter-card,
.topic-shell,
.timeline-shell {
  background: rgba(255, 251, 244, 0.92);
  border: 1px solid #e6dccd;
  border-radius: 20px;
  box-shadow: 0 14px 30px rgba(82, 61, 34, 0.08);
}
.story-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 22px;
  margin-bottom: 18px;
}
.eyebrow {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .12em;
  color: #8f6741;
  margin-bottom: 8px;
}
.story-header h1,
.chapter-card h2,
.topic-header h3 {
  margin: 0;
  font-family: Georgia, "Noto Serif SC", serif;
}
.premise {
  margin: 10px 0 0;
  max-width: 720px;
  line-height: 1.6;
  color: #665a4e;
}
.header-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.status-pill,
.ghost-btn,
.primary-btn,
.topic-card {
  border-radius: 999px;
  font: inherit;
}
.status-pill {
  padding: 8px 12px;
  background: #e9dfcf;
  color: #5d5145;
}
.status-pill.processing { background: #e7d9be; color: #6e5324; }
.status-pill.ready { background: #d9eadf; color: #24523a; }
.status-pill.error { background: #f2d5d5; color: #7a2424; }
.ghost-btn,
.primary-btn {
  border: 0;
  cursor: pointer;
  padding: 10px 14px;
}
.ghost-btn {
  background: #ece1d0;
  color: #53493f;
}
.primary-btn {
  background: #214b43;
  color: #fff;
}
.ghost-btn:disabled,
.primary-btn:disabled,
.topic-card:disabled {
  opacity: .6;
  cursor: default;
}
.chapter-shell {
  margin-bottom: 18px;
}
.chapter-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
  color: #7d6b57;
  font-size: 13px;
}
.chapter-card {
  padding: 24px;
}
.chapter-summary {
  margin: 10px 0 18px;
  color: #6d5f50;
}
.chapter-content {
  font-family: Georgia, "Noto Serif SC", serif;
  line-height: 1.9;
  font-size: 16px;
}
.chapter-content :deep(p) {
  margin: 0 0 1em;
}
.placeholder {
  display: grid;
  place-items: center;
  min-height: 260px;
  margin-bottom: 18px;
}
.topic-shell,
.timeline-shell {
  padding: 20px;
  margin-bottom: 18px;
}
.topic-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
.topic-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.topic-card {
  border: 1px solid #e5d7c6;
  background: #fffdf8;
  text-align: left;
  padding: 16px;
  cursor: pointer;
}
.topic-card:hover:not(:disabled) {
  border-color: #214b43;
  transform: translateY(-1px);
}
.topic-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: #8a725d;
}
.topic-card h4 {
  margin: 12px 0 8px;
  font-size: 18px;
  font-family: Georgia, "Noto Serif SC", serif;
}
.topic-card p {
  margin: 0;
  color: #5f5449;
  line-height: 1.6;
}
.topic-characters {
  margin-top: 12px;
  color: #7e6a58;
  font-size: 12px;
}
.topic-loading,
.timeline-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #6b6055;
  min-height: 56px;
}
.timeline-list {
  display: grid;
  gap: 10px;
}
.timeline-item {
  display: flex;
  gap: 12px;
  border: 1px solid #ecdfcf;
  border-radius: 14px;
  background: #fffdf8;
  padding: 12px 14px;
}
.timeline-no {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #f0e4d1;
  display: grid;
  place-items: center;
  font-weight: 700;
  color: #5e4c38;
}
.timeline-title {
  font-weight: 700;
  margin-bottom: 4px;
}
.timeline-summary {
  color: #706356;
  font-size: 14px;
}
.spinner {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 3px solid #dfd4c4;
  border-top-color: #214b43;
  animation: spin 0.9s linear infinite;
}
.spinner.small {
  width: 18px;
  height: 18px;
  border-width: 2px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 980px) {
  .story-header,
  .topic-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .topic-grid {
    grid-template-columns: 1fr;
  }
}
</style>
