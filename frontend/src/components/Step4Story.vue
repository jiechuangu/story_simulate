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
        <button
          v-if="latestChapter"
          class="ghost-btn"
          :disabled="retrying || isGenerating || !storySession"
          @click="restartStory"
        >
          {{ retrying ? 'Regenerating...' : 'Regenerate Chapter' }}
        </button>
      </div>
    </section>

    <section v-if="showBlueprint" class="blueprint-shell">
      <div class="topic-header">
        <div>
          <div class="eyebrow">Blueprint</div>
          <h3>Review the story setup before chapter generation</h3>
        </div>
      </div>

      <div v-if="blueprint" class="blueprint-card">
        <div class="blueprint-grid">
          <div>
            <div class="label">Summary</div>
            <div>{{ blueprint.story_summary || storyPremise }}</div>
          </div>
          <div>
            <div class="label">Conflict</div>
            <div>{{ blueprint.core_conflict || 'Pending' }}</div>
          </div>
          <div>
            <div class="label">Protagonist</div>
            <div>{{ blueprint.protagonist?.name || 'Pending' }}</div>
          </div>
          <div>
            <div class="label">Graph Bootstrap</div>
            <div>{{ graphBootstrapText }}</div>
          </div>
        </div>

        <div class="outline-box">
          <pre>{{ outlineMarkdown }}</pre>
        </div>

        <div class="instruction-box">
          <textarea
            v-model="blueprintInstruction"
            class="instruction-input"
            placeholder="Optional: ask for a different direction, tone, or constraint"
            rows="3"
            :disabled="isGenerating || confirming"
          ></textarea>
        </div>

        <div class="blueprint-actions">
          <button class="ghost-btn" :disabled="isGenerating || confirming" @click="handleRegenerateBlueprint('')">
            Regenerate Blueprint
          </button>
          <button class="ghost-btn" :disabled="isGenerating || confirming || !blueprintInstruction.trim()" @click="handleRegenerateBlueprint(blueprintInstruction)">
            Regenerate With Input
          </button>
          <button class="primary-btn" :disabled="isGenerating || confirming" @click="handleConfirmBlueprint">
            {{ confirming ? 'Generating Chapter 1...' : 'Accept Blueprint' }}
          </button>
        </div>
      </div>

      <div v-else class="chapter-card placeholder">
        <div class="spinner"></div>
        <p>Generating blueprint and ontology...</p>
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

    <section v-else-if="!showBlueprint" class="chapter-card placeholder">
      <div class="spinner"></div>
      <p>Generating the current chapter...</p>
    </section>

    <section v-if="latestChapter" class="topic-shell">
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
          <div v-if="formatFocusCharacters(topic.focus_characters)" class="topic-characters">
            {{ formatFocusCharacters(topic.focus_characters) }}
          </div>
        </button>
      </div>
    </section>

    <section class="timeline-shell">
      <div class="topic-header">
        <div>
          <div class="eyebrow">Progress</div>
          <h3>{{ latestChapter ? 'Chapter Timeline' : 'Blueprint State' }}</h3>
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
import {
  confirmBlueprint,
  getStorySession,
  regenerateBlueprint,
  restartCurrentChapter,
  selectNextTopic
} from '../api/story'

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
const confirming = ref(false)
const blueprintInstruction = ref('')
let pollTimer = null

const log = (msg) => emit('add-log', msg)

const showBlueprint = computed(() => {
  return !!storySession.value && !latestChapter.value
})

const statusClass = computed(() => {
  if (!storySession.value) return 'processing'
  if (storySession.value.status === 'failed') return 'error'
  if (storySession.value.status === 'generating' || storySession.value.status === 'pending') return 'processing'
  return 'ready'
})

const statusLabel = computed(() => {
  if (!storySession.value) return 'Loading'
  if (storySession.value.status === 'failed') return 'Error'
  if (storySession.value.status === 'waiting_for_confirmation') return 'Review Blueprint'
  if (storySession.value.status === 'waiting_for_choice') return 'Waiting for Choice'
  return 'Generating'
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
const blueprint = computed(() => storySession.value?.blueprint || null)
const outlineMarkdown = computed(() => storySession.value?.outline_markdown || 'No outline yet.')
const graphBootstrapText = computed(() => {
  const bootstrap = storySession.value?.graph_bootstrap || {}
  if (!bootstrap.status) return 'Pending'
  if (bootstrap.status === 'ready') {
    return `Ready (${bootstrap.node_count || 0} nodes / ${bootstrap.edge_count || 0} edges)`
  }
  if (bootstrap.status === 'failed') {
    return `Failed: ${bootstrap.error || 'unknown error'}`
  }
  return bootstrap.status
})
const canGoToInteraction = computed(() => !!props.storyId && !!latestChapter.value)

const renderChapter = (text) => {
  if (!text) return ''
  return text
    .split(/\n{2,}/)
    .map((block) => `<p>${block.replace(/\n/g, '<br>')}</p>`)
    .join('')
}

const formatFocusCharacters = (value) => {
  if (Array.isArray(value)) {
    return value.filter(Boolean).join(' / ')
  }
  if (typeof value === 'string') {
    return value
      .split(/[、,]/)
      .map(item => item.trim())
      .filter(Boolean)
      .join(' / ')
  }
  return ''
}

const refreshStorySession = async () => {
  if (!props.storyId) return
  try {
    const res = await getStorySession(props.storyId)
    storySession.value = res.data
    if (storySession.value.status === 'failed') {
      emit('update-status', 'error')
      stopPolling()
    } else if (storySession.value.status === 'waiting_for_confirmation' || storySession.value.status === 'waiting_for_choice') {
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

const handleConfirmBlueprint = async () => {
  if (!props.storyId || confirming.value) return
  confirming.value = true
  emit('update-status', 'processing')
  try {
    log(`Blueprint accepted: ${props.storyId}`)
    await confirmBlueprint(props.storyId)
    if (storySession.value) {
      storySession.value.status = 'generating'
    }
    startPolling()
    await refreshStorySession()
  } catch (err) {
    log(`Confirm blueprint failed: ${err.message}`)
    emit('update-status', 'error')
  } finally {
    confirming.value = false
  }
}

const handleRegenerateBlueprint = async (instruction) => {
  if (!props.storyId || isGenerating.value) return
  emit('update-status', 'processing')
  try {
    log(`Regenerating blueprint${instruction ? `: ${instruction}` : ''}`)
    await regenerateBlueprint(props.storyId, instruction ? { instruction } : {})
    if (storySession.value) {
      storySession.value.status = 'generating'
    }
    startPolling()
    await refreshStorySession()
    blueprintInstruction.value = ''
  } catch (err) {
    log(`Regenerate blueprint failed: ${err.message}`)
    emit('update-status', 'error')
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
  if (retrying.value || !props.storyId) return
  retrying.value = true
  try {
    log(`Regenerating current chapter: ${props.storyId}`)
    await restartCurrentChapter(props.storyId)
    if (storySession.value) {
      storySession.value.status = 'generating'
      storySession.value.topic_candidates = []
    }
    emit('update-status', 'processing')
    startPolling()
    await refreshStorySession()
  } catch (err) {
    log(`Regenerate chapter failed: ${err.message}`)
    emit('update-status', 'error')
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
.timeline-shell,
.blueprint-shell {
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
  gap: 12px;
}
.status-pill,
.ghost-btn,
.primary-btn,
.topic-card {
  border-radius: 999px;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
}
.status-pill.processing {
  background: #fff2d8;
  color: #8b5a00;
}
.status-pill.ready {
  background: #e7f7e7;
  color: #1e6b35;
}
.status-pill.error {
  background: #fde8e7;
  color: #a3362a;
}
.ghost-btn,
.primary-btn {
  border: 1px solid #d5c4b0;
  padding: 10px 16px;
  background: #fff;
  cursor: pointer;
}
.primary-btn {
  background: #221f1b;
  color: #fff;
  border-color: #221f1b;
}
.ghost-btn:disabled,
.primary-btn:disabled,
.topic-card:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.blueprint-shell,
.topic-shell,
.timeline-shell {
  padding: 20px;
  margin-bottom: 18px;
}
.blueprint-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.blueprint-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.label {
  font-size: 12px;
  text-transform: uppercase;
  color: #8f6741;
  margin-bottom: 4px;
}
.outline-box {
  border: 1px solid #eadfce;
  background: #fffdf8;
  border-radius: 16px;
  padding: 14px;
}
.outline-box pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  line-height: 1.6;
}
.instruction-input {
  width: 100%;
  border: 1px solid #decdb6;
  border-radius: 14px;
  padding: 12px;
  resize: vertical;
  font: inherit;
}
.blueprint-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.chapter-shell {
  margin-bottom: 18px;
}
.chapter-meta {
  display: flex;
  justify-content: space-between;
  padding: 0 8px 10px;
  color: #8b7055;
}
.chapter-card {
  padding: 22px;
}
.chapter-summary {
  color: #695948;
  line-height: 1.6;
}
.chapter-content {
  line-height: 1.85;
}
.chapter-content :deep(p) {
  margin: 0 0 16px;
}
.placeholder,
.topic-loading,
.timeline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #7c6a58;
  min-height: 160px;
}
.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #eadfce;
  border-top-color: #8f6741;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
.spinner.small {
  width: 20px;
  height: 20px;
}
.topic-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}
.topic-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}
.topic-card {
  border: 1px solid #e8dbcb;
  padding: 18px;
  text-align: left;
  background: #fff;
  cursor: pointer;
}
.topic-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #8b7055;
  font-size: 12px;
  margin-bottom: 10px;
}
.topic-card h4 {
  margin: 0 0 8px;
}
.topic-card p {
  margin: 0;
  line-height: 1.6;
  color: #5f5247;
}
.topic-characters {
  margin-top: 12px;
  font-size: 12px;
  color: #7a634e;
}
.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.timeline-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: 14px;
  background: #fffaf1;
}
.timeline-no {
  min-width: 40px;
  font-family: "JetBrains Mono", monospace;
  color: #8b7055;
}
.timeline-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.timeline-summary {
  color: #665a4e;
  line-height: 1.5;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
