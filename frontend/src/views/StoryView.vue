<template>
  <div class="page" v-if="story">
    <header class="top">
      <router-link to="/" class="btn small">← 返回</router-link>
      <h1>{{ bp?.title || '生成中…' }}</h1>
      <span class="spacer" />
      <button class="btn small" :disabled="busy" @click="toggleStyleEditor">文风：{{ styleName(story.style_id) }} ▾</button>
      <a v-if="story.chapters.length" class="btn small" :href="api.downloadUrl(id)">下载 Markdown</a>
    </header>

    <!-- 任务状态 -->
    <div v-if="story.status === 'generating'" class="card status">
      <div class="status-row">
        <span>{{ story.job?.message || '处理中' }}</span>
        <span class="muted">{{ story.job?.progress || 0 }}%</span>
      </div>
      <div class="progress"><div :style="{ width: (story.job?.progress || 2) + '%' }" /></div>
    </div>
    <div v-if="story.status === 'failed'" class="card status">
      <p class="error">生成失败：{{ story.error }}</p>
      <button class="btn primary" @click="act(() => api.retry(id))">重试</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="styleEditing" class="card style-editor">
      <p class="muted">切换后对之后生成的内容生效：重新生成蓝图、下一章、重写本章。已写好的章节不变。</p>
      <StylePicker v-model="styleDraft" v-model:notes="styleNotesDraft" :styles="styles" :disabled="busy" />
      <div class="row">
        <button class="btn primary" :disabled="busy" @click="saveStyle">保存文风</button>
        <button class="btn" @click="styleEditing = false">取消</button>
      </div>
    </div>

    <!-- 蓝图阶段 -->
    <section v-if="bp && !story.chapters.length" class="blueprint">
      <div class="card">
        <p class="premise">{{ bp.premise }}</p>
        <p class="summary">{{ bp.summary }}</p>
        <dl>
          <dt>题材</dt><dd>{{ bp.genre }}</dd>
          <dt>设定</dt><dd>{{ bp.setting }}</dd>
          <dt>文风</dt><dd>{{ bp.style }}</dd>
          <dt>核心矛盾</dt><dd>{{ bp.core_conflict }}</dd>
          <dt>开场情境</dt><dd>{{ bp.opening_situation }}</dd>
          <dt>大致走向</dt><dd>{{ bp.ending_direction }}</dd>
          <dt v-if="bp.selling_points?.length">卖点</dt>
          <dd v-if="bp.selling_points?.length"><ul><li v-for="x in bp.selling_points" :key="x">{{ x }}</li></ul></dd>
          <dt v-if="bp.reader_promises?.length">读者期待</dt>
          <dd v-if="bp.reader_promises?.length"><ul><li v-for="x in bp.reader_promises" :key="x">{{ x }}</li></ul></dd>
          <dt v-if="bp.rules.length">世界规则</dt>
          <dd v-if="bp.rules.length"><ul><li v-for="r in bp.rules" :key="r">{{ r }}</li></ul></dd>
        </dl>
      </div>
      <h3>人物</h3>
      <div class="chars">
        <div v-for="c in bp.characters" :key="c.name" class="card">
          <div class="char-head"><strong>{{ c.name }}</strong><span class="tag">{{ c.role }}</span></div>
          <p>{{ c.description }}</p>
          <p class="muted">性格：{{ c.personality }}</p>
          <p class="muted">说话：{{ c.voice }}</p>
          <p class="muted">目标：{{ c.goal }}</p>
          <p v-if="c.secret" class="muted">秘密：{{ c.secret }}</p>
        </div>
      </div>
      <div v-if="bp.relationships.length" class="card">
        <h3>关系</h3>
        <ul class="rels"><li v-for="(r, i) in bp.relationships" :key="i"><b>{{ r.from }}</b> → <b>{{ r.to }}</b>：{{ r.description }}</li></ul>
      </div>
      <div class="card actions">
        <textarea v-model="instruction" rows="3" placeholder="对蓝图不满意？写下修改意见，例如：主角改成女性；去掉超自然元素；节奏更日常一些……" />
        <div class="row">
          <button class="btn" :disabled="busy" @click="act(() => api.regenerateBlueprint(id, instruction)).then(() => (instruction = ''))">
            按意见重新生成
          </button>
          <button class="btn primary" :disabled="busy" @click="act(() => api.confirmBlueprint(id))">确认蓝图，开始第一章</button>
        </div>
      </div>
    </section>

    <!-- 章节阶段 -->
    <section v-if="story.chapters.length" class="reader">
      <aside class="toc">
        <h3>目录</h3>
        <div
          v-for="ch in story.chapters"
          :key="ch.no"
          class="toc-item"
          :class="{ active: ch.no === current?.no }"
          @click="viewNo = ch.no"
        >
          <span>第{{ ch.no }}章 {{ ch.title }}</span>
          <button
            v-if="ch.no < story.chapters.length"
            class="btn small"
            title="删除之后的章节，回到本章结束时的状态重新选择"
            :disabled="busy"
            @click.stop="rewind(ch.no)"
          >回到此处</button>
        </div>
      </aside>

      <main class="chapter" v-if="current">
        <div class="tabs">
          <button v-for="t in tabs" :key="t.key" class="tab" :class="{ on: tab === t.key }" @click="tab = t.key">{{ t.label }}</button>
        </div>
        <article v-if="tab === 'text'">
          <h2>第{{ current.no }}章 {{ current.title }}</h2>
          <p class="muted meta">
            {{ current.time_label }} · 视角：{{ nameOf(current.pov) }}
            <template v-if="current.topic"> · 方向：{{ current.topic.title }}</template>
            <template v-if="current.style_id"> · 文风：{{ styleName(current.style_id) }}</template>
          </p>
          <p v-if="current.pacing" class="muted meta pacing">节奏任务：{{ current.pacing }}</p>
          <p v-if="current.introduced?.length" class="muted meta pacing">新登场：{{ current.introduced.map(nameOf).join('、') }}</p>
          <div class="prose">
            <p v-for="(para, i) in paragraphs(current.content)" :key="i">{{ para }}</p>
          </div>
        </article>
        <div v-else-if="tab === 'events'" class="events">
          <p class="muted hint">这是本章世界里实际发生的事（角色在各自信息范围内自主行动的结果），正文据此写成。</p>
          <div v-for="(sc, i) in current.scenes" :key="i" class="scene">
            <h4>场景{{ i + 1 }} · {{ sc.location }}</h4>
            <p class="muted">{{ sc.situation }}　在场：{{ sc.present.map(nameOf).join('、') }}</p>
            <ul>
              <li v-for="e in current.events.filter((e) => e.scene_no === i + 1)" :key="e.id" :class="e.kind">
                <template v-if="e.kind === 'world'">（{{ e.content }}）</template>
                <template v-else-if="e.kind === 'speech'"><b>{{ nameOf(e.actor) }}</b>：“{{ e.content }}”</template>
                <template v-else><b>{{ nameOf(e.actor) }}</b> {{ e.content }}</template>
              </li>
            </ul>
          </div>
          <div v-if="current.consistency_notes.length" class="scene">
            <h4>设定审校修正</h4>
            <ul><li v-for="n in current.consistency_notes" :key="n" class="muted">{{ n }}</li></ul>
          </div>
        </div>
        <div v-else-if="tab === 'draft'" class="prose">
          <p class="muted hint">润色前的初稿，用来对比“去 AI 腔”修改了什么。</p>
          <p v-for="(para, i) in paragraphs(current.draft)" :key="i">{{ para }}</p>
        </div>

        <div v-if="isLatest && story.status === 'awaiting_choice'" class="next">
          <p class="muted summary-line">本章摘要：{{ current.summary }}</p>
          <h3>下一章往哪走？</h3>
          <div class="topics">
            <button v-for="t in story.topics" :key="t.id" class="card topic" :disabled="busy" @click="act(() => api.choose(id, { topic_id: t.id }))">
              <strong>{{ t.title }}</strong>
              <span>{{ t.summary }}</span>
              <span v-if="t.focus_characters.length" class="muted">{{ t.focus_characters.join('、') }}</span>
            </button>
          </div>
          <div class="row">
            <input v-model="custom" type="text" placeholder="或者自己写方向……" @keyup.enter="chooseCustom" />
            <button class="btn" :disabled="busy || !custom.trim()" @click="chooseCustom">按我的方向写</button>
            <button class="btn" :disabled="busy" @click="act(() => api.regenerateChapter(id))">重写本章</button>
          </div>
        </div>
      </main>

      <aside class="world" v-if="story.world">
        <h3>世界状态</h3>
        <p class="muted">{{ story.world.time_label }}</p>
        <div
          v-for="c in story.world.characters"
          :key="c.id"
          class="wchar"
          :class="{ inactive: !c.active, open: openChar === c.id }"
          @click="openChar = openChar === c.id ? '' : c.id"
        >
          <div class="char-head">
            <strong>{{ c.name }}</strong>
            <span class="muted">{{ c.active ? c.location : '已离场' }}</span>
          </div>
          <span v-if="c.introduced_in" class="tag new">第{{ c.introduced_in }}章登场</span>
          <p class="muted">{{ [c.mood, c.status].filter(Boolean).join(' · ') }}</p>
          <div v-if="openChar === c.id" class="detail">
            <p><b>目标</b> {{ c.goal }}</p>
            <p><b>知道的事</b></p>
            <ul><li v-for="f in knownBy(c.id)" :key="f.id">{{ f.content }}</li></ul>
            <p v-if="Object.keys(c.relationships).length"><b>看待他人</b></p>
            <ul><li v-for="(d, oid) in c.relationships" :key="oid">{{ nameOf(oid) }}：{{ d }}</li></ul>
          </div>
        </div>
        <template v-if="story.world.open_threads.length">
          <h3>未解决的线索</h3>
          <ul class="threads"><li v-for="t in story.world.open_threads" :key="t">{{ t }}</li></ul>
        </template>
      </aside>
    </section>
  </div>
  <div v-else class="page"><p class="muted">{{ error || '加载中…' }}</p></div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import StylePicker from '../components/StylePicker.vue'

const styles = ref([])
const styleEditing = ref(false)
const styleDraft = ref('')
const styleNotesDraft = ref('')
const styleName = (sid) => styles.value.find((s) => s.id === sid)?.name || sid || '写实文学'

const toggleStyleEditor = () => {
  styleEditing.value = !styleEditing.value
  styleDraft.value = story.value?.style_id || 'realistic'
  styleNotesDraft.value = story.value?.style_notes || ''
}

const saveStyle = async () => {
  await act(() => api.setStyle(id, styleDraft.value, styleNotesDraft.value))
  if (!error.value) styleEditing.value = false
}

const props = defineProps({ id: { type: String, required: true } })
const id = props.id
const story = ref(null)
const error = ref('')
const instruction = ref('')
const custom = ref('')
const viewNo = ref(0)
const tab = ref('text')
const openChar = ref('')
const tabs = [
  { key: 'text', label: '正文' },
  { key: 'events', label: '幕后：事件记录' },
  { key: 'draft', label: '润色前初稿' }
]
let timer = null

const bp = computed(() => story.value?.blueprint)
const busy = computed(() => story.value?.status === 'generating')
const current = computed(() => {
  const chs = story.value?.chapters || []
  return chs.find((c) => c.no === viewNo.value) || chs[chs.length - 1]
})
const isLatest = computed(() => current.value && current.value.no === story.value.chapters.length)

const nameOf = (cid) => story.value?.world?.characters.find((c) => c.id === cid)?.name || cid
const knownBy = (cid) => (story.value?.world?.facts || []).filter((f) => f.public || f.known_by.includes(cid))
const paragraphs = (text) => (text || '').split(/\n+/).map((s) => s.trim()).filter(Boolean)

const load = async () => {
  try {
    const prevCount = story.value?.chapters.length || 0
    story.value = await api.get(id)
    if (story.value.chapters.length !== prevCount) {
      viewNo.value = story.value.chapters.length
      tab.value = 'text'
    }
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

const act = async (fn) => {
  error.value = ''
  try {
    story.value = await fn()
  } catch (e) {
    error.value = e.message
  }
}

const chooseCustom = () => {
  if (!custom.value.trim() || busy.value) return
  act(() => api.choose(id, { custom: custom.value })).then(() => (custom.value = ''))
}

const rewind = (no) => {
  if (!confirm(`删除第 ${no} 章之后的所有章节，回到第 ${no} 章结束时重新选择方向？`)) return
  act(() => api.rewind(id, no)).then(() => (viewNo.value = no))
}

watch(busy, (b) => {
  clearInterval(timer)
  if (b) timer = setInterval(load, 2000)
})

onMounted(async () => {
  api.styles().then((s) => (styles.value = s)).catch(() => {})
  await load()
  if (busy.value) timer = setInterval(load, 2000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 20px 16px 60px; display: flex; flex-direction: column; gap: 16px; }
.top { display: flex; align-items: center; gap: 14px; }
.top h1 { font-family: var(--serif); font-size: 24px; }
.spacer { flex: 1; }
h3 { font-size: 14px; margin: 4px 0 10px; }
.style-editor { display: flex; flex-direction: column; gap: 10px; }
.pacing { margin-top: -14px; }
.status { display: flex; flex-direction: column; gap: 8px; }
.status-row { display: flex; justify-content: space-between; }
.row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.row input { flex: 1; min-width: 200px; }

.blueprint { display: flex; flex-direction: column; gap: 14px; max-width: 980px; }
.premise { font-family: var(--serif); font-size: 18px; margin-bottom: 8px; }
.summary { margin-bottom: 14px; }
dl { display: grid; grid-template-columns: 90px 1fr; gap: 6px 12px; }
dt { color: var(--muted); }
dd ul, .rels, .threads, .detail ul { padding-left: 18px; }
.chars { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.chars .card p { font-size: 13px; margin-top: 4px; }
.char-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.actions { display: flex; flex-direction: column; gap: 10px; }

.reader { display: grid; grid-template-columns: 220px minmax(0, 1fr) 280px; gap: 18px; align-items: start; }
.toc, .world { position: sticky; top: 16px; max-height: calc(100vh - 32px); overflow: auto; }
.toc-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.toc-item:hover { background: #ece8e0; }
.toc-item.active { background: var(--accent-soft); color: var(--accent); }

.chapter { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 24px 40px 32px; min-width: 0; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin: -8px 0 20px; }
.tab { border: none; background: none; padding: 8px 12px; cursor: pointer; font: inherit; color: var(--muted); border-bottom: 2px solid transparent; }
.tab.on { color: var(--accent); border-color: var(--accent); }
article h2 { font-family: var(--serif); font-size: 22px; }
.meta { margin: 4px 0 20px; font-size: 12px; }
.prose p { font-family: var(--serif); font-size: 17px; line-height: 1.95; text-indent: 2em; margin-bottom: .9em; }
.prose .hint, .hint { text-indent: 0; font-family: var(--sans); font-size: 13px; margin-bottom: 14px; }
.scene { margin-bottom: 18px; }
.scene h4 { margin-bottom: 4px; }
.scene ul { list-style: none; margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.scene li.world { color: var(--muted); font-style: italic; }

.next { margin-top: 32px; padding-top: 20px; border-top: 1px dashed var(--line); display: flex; flex-direction: column; gap: 12px; }
.summary-line { font-size: 13px; }
.topics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
.topic { text-align: left; cursor: pointer; display: flex; flex-direction: column; gap: 6px; font: inherit; color: inherit; }
.topic:hover:not(:disabled) { border-color: var(--accent); }
.topic:disabled { opacity: .5; cursor: not-allowed; }

.world .wchar { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; cursor: pointer; font-size: 13px; }
.wchar.inactive { opacity: .5; }
.wchar .tag.new { margin-top: 4px; font-size: 11px; }
.wchar.open { border-color: var(--accent); }
.detail { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
.threads { font-size: 13px; }

@media (max-width: 1100px) {
  .reader { grid-template-columns: 1fr; }
  .toc, .world { position: static; max-height: none; }
  .chapter { padding: 20px 16px; }
}
</style>
