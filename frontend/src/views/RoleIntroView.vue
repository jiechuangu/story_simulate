<template>
  <div class="intro-view">
    <header class="topbar">
      <button class="ghost-btn" @click="goBack">Back to Step 5</button>
      <div class="title-wrap">
        <div class="step">Role Briefing</div>
        <h1>{{ characterName || 'Character Intro' }}</h1>
      </div>
      <div class="meta">{{ currentIndex + 1 }} / {{ totalSlides }}</div>
    </header>

    <main class="content" v-if="ready">
      <section class="story-card">
        <div class="frame">
          <img v-if="currentSlide?.imageUrl" :src="currentSlide.imageUrl" :alt="currentSlide?.title || 'story image'" />
          <div v-else class="frame-loading">
            <div class="ring"></div>
            <p>{{ generating ? 'Generating image and story...' : 'Image not ready' }}</p>
          </div>
        </div>
        <div class="story-text">
          <h2>{{ currentSlide?.title || 'Preparing...' }}</h2>
          <p>{{ currentSlide?.text || 'Building role context from graph knowledge...' }}</p>
        </div>
      </section>

      <aside class="source-card">
        <h3>Knowledge Sources</h3>
        <ul>
          <li v-for="(source, idx) in currentSlide?.sources || []" :key="`${idx}-${source}`">{{ source }}</li>
        </ul>
      </aside>
    </main>

    <footer class="actions" v-if="ready">
      <button class="ghost-btn" :disabled="currentIndex === 0 || generating" @click="prevSlide">Prev</button>
      <button class="primary-btn" :disabled="generating || currentIndex >= totalSlides - 1" @click="nextSlide">Next</button>
      <button class="enter-btn" :disabled="generating || currentIndex < totalSlides - 1" @click="enterStep6">Enter Step 6</button>
    </footer>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getStorySession } from '../api/story'
import { bootstrapWorld, createWorldImageTask, listWorldImageTasks, fetchWorldIntroPlan } from '../api/world'

const route = useRoute()
const router = useRouter()

const storyId = route.params.storyId
const characterId = route.params.characterId

const ready = ref(false)
const generating = ref(false)
const currentIndex = ref(0)
const simulationId = ref('')
const worldState = ref(null)
const character = ref(null)
const slides = ref([])

const characterName = computed(() => character.value?.name || '')
const currentSlide = computed(() => slides.value[currentIndex.value] || null)
const totalSlides = computed(() => Math.max(1, slides.value.length))

const goBack = () => {
  router.push({ name: 'Interaction', params: { storyId } })
}

const enterStep6 = () => {
  router.push({ name: 'RoleControl', params: { storyId, characterId } })
}

const pickCharacter = () => {
  const chars = worldState.value?.characters || []
  character.value = chars.find(item => item.character_id === characterId) || null
}

const baseName = computed(() => {
  const n = characterName.value || ''
  return n.split('_')[0] || n
})

const initSlidesFromPlan = (plan) => {
  const rawSlides = Array.isArray(plan?.slides) ? plan.slides : []
  slides.value = rawSlides.map((item, idx) => ({
    index: idx,
    title: item?.title || `章节 ${idx + 1}`,
    text: item?.text || `${baseName.value} 的剧情背景正在整理中。`,
    sources: Array.isArray(item?.sources) ? item.sources : [],
    taskId: '',
    imageUrl: '',
    status: 'pending'
  }))
  if (!slides.value.length) {
    slides.value = Array.from({ length: 3 }, (_, idx) => ({
      index: idx,
      title: `章节 ${idx + 1}`,
      text: `${baseName.value} 的剧情背景正在整理中。`,
      sources: [],
      taskId: '',
      imageUrl: '',
      status: 'pending'
    }))
  }
  currentIndex.value = 0
}

const initFallbackSlides = () => {
  slides.value = Array.from({ length: 3 }, (_, idx) => ({
    index: idx,
    title: `章节 ${idx + 1}`,
    text: `${baseName.value || '该角色'} 的引导信息加载中，你可以先查看并等待图像生成。`,
    sources: [],
    taskId: '',
    imageUrl: '',
    status: 'pending'
  }))
  currentIndex.value = 0
}

const buildImagePrompt = (idx, text) => {
  const role = character.value
  const appearance = (role?.appearance_notes || []).slice(0, 3).join('; ') || 'distinctive literary character look'
  const phase = idx + 1
  return [
    `Cinematic story frame ${phase}/10 for ${baseName.value}.`,
    `Character appearance: ${appearance}.`,
    `Narrative scene: ${text}`,
    `World context: ${worldState.value?.world_name || 'Novel world'}.`,
    'Illustrated novel frame, strong composition, no text watermark, high detail.'
  ].join(' ')
}

const waitImageReady = async (taskId, maxRound = 45) => {
  for (let i = 0; i < maxRound; i += 1) {
    const res = await listWorldImageTasks(simulationId.value)
    const tasks = res?.data || []
    const target = tasks.find(task => task.task_id === taskId)
    if (target && target.status === 'completed') return { ok: true, task: target }
    if (target && target.status === 'failed') return { ok: false, task: target }
    await new Promise(resolve => setTimeout(resolve, 1200))
  }
  return { ok: false, task: null }
}

const ensureSlide = async (idx) => {
  const slide = slides.value[idx]
  if (!slide || slide.status === 'completed') return
  generating.value = true
  try {
    const prompt = buildImagePrompt(idx, slide.text || `${baseName.value} 的剧情片段`)
    const createRes = await createWorldImageTask(simulationId.value, {
      character_id: characterId,
      prompt_override: prompt,
      style: 'storyboard-cinematic',
      auto_generate: true
    })
    const task = createRes?.data
    slide.taskId = task?.task_id || ''
    slide.status = task?.status || 'queued'
    if (slide.taskId) {
      const readyRes = await waitImageReady(slide.taskId)
      if (readyRes.ok) {
        slide.status = 'completed'
        slide.imageUrl = `/api/world/${simulationId.value}/image-tasks/${slide.taskId}/file`
      } else {
        slide.status = 'failed'
      }
    }
  } finally {
    generating.value = false
  }
}

const nextSlide = async () => {
  const next = currentIndex.value + 1
  if (next >= slides.value.length) return
  currentIndex.value = next
  await ensureSlide(next)
}

const prevSlide = () => {
  const prev = currentIndex.value - 1
  if (prev < 0) return
  currentIndex.value = prev
}

onMounted(async () => {
  try {
    const storyRes = await getStorySession(storyId)
    simulationId.value = storyRes?.data?.simulation_id || ''
    if (!simulationId.value) return

    const worldRes = await bootstrapWorld({ simulation_id: simulationId.value })
    worldState.value = worldRes?.data || null
    pickCharacter()
    ready.value = true
    initFallbackSlides()
    generating.value = true
    try {
      const introRes = await Promise.race([
        fetchWorldIntroPlan(simulationId.value, { character_id: characterId }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('intro-plan timeout')), 35000))
      ])
      initSlidesFromPlan(introRes?.data || null)
    } catch (e) {
      // 保留 fallback slides，避免黑屏
    } finally {
      generating.value = false
    }
    await ensureSlide(0)
  } catch (e) {
    ready.value = false
  }
})
</script>

<style scoped>
.intro-view { min-height: 100vh; background: #111; color: #f8f5ef; display: flex; flex-direction: column; }
.topbar { height: 68px; display: flex; align-items: center; justify-content: space-between; padding: 0 22px; border-bottom: 1px solid rgba(255,255,255,.14); }
.title-wrap { text-align: center; }
.step { font-size: 11px; color: #b8b1a5; letter-spacing: .12em; text-transform: uppercase; }
.title-wrap h1 { margin: 2px 0 0; font-size: 20px; }
.meta { font-family: 'JetBrains Mono', monospace; color: #c9c0b2; }
.content { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; padding: 18px; flex: 1; min-height: 0; }
.story-card, .source-card { background: #1c1a17; border: 1px solid #3a352d; border-radius: 14px; padding: 14px; }
.frame { border-radius: 12px; overflow: hidden; background: #2b2721; aspect-ratio: 16/9; display: grid; place-items: center; }
.frame img { width: 100%; height: 100%; object-fit: cover; display: block; }
.frame-loading { display: grid; place-items: center; gap: 10px; color: #b9ae9c; }
.ring { width: 28px; height: 28px; border: 3px solid rgba(255,255,255,.15); border-top-color: #d9c9ae; border-radius: 50%; animation: spin 1s linear infinite; }
.story-text { margin-top: 12px; }
.story-text h2 { margin: 0 0 8px; font-size: 18px; }
.story-text p { margin: 0; color: #d2c9bc; line-height: 1.6; }
.source-card h3 { margin: 0 0 10px; font-size: 15px; }
.source-card ul { margin: 0; padding-left: 18px; display: grid; gap: 8px; max-height: calc(100vh - 240px); overflow: auto; }
.source-card li { color: #c7beaf; font-size: 13px; line-height: 1.45; }
.actions { height: 70px; display: flex; align-items: center; justify-content: center; gap: 10px; border-top: 1px solid rgba(255,255,255,.14); }
.primary-btn, .ghost-btn, .enter-btn { border: 0; border-radius: 999px; padding: 9px 14px; cursor: pointer; font: inherit; }
.primary-btn { background: #f0debe; color: #2a241c; }
.ghost-btn { background: #2b2721; color: #e0d4c1; border: 1px solid #4b4338; }
.enter-btn { background: #1f6f57; color: #fff; }
.primary-btn:disabled, .ghost-btn:disabled, .enter-btn:disabled { opacity: .45; cursor: not-allowed; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 980px) {
  .content { grid-template-columns: 1fr; }
  .source-card ul { max-height: 220px; }
}
</style>
