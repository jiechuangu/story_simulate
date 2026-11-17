<template>
  <div class="home">
    <header>
      <h1>Story Simulate</h1>
      <p class="muted">先让世界里的人物行动起来，再把发生的事写成小说。每章结束后由你决定下一章的方向。</p>
    </header>

    <section class="card create">
      <h2>新故事</h2>
      <textarea
        v-model="seed"
        rows="6"
        placeholder="写下故事需求：题材、时代、主角、你想看的矛盾……也可以只上传素材，让系统据此续写或改编。"
      />
      <h3>文风</h3>
      <StylePicker v-model="style" v-model:notes="styleNotes" :styles="styles" />
      <div class="row">
        <label class="btn">
          上传素材（txt / md / pdf）
          <input type="file" multiple accept=".txt,.md,.markdown,.pdf" hidden @change="onFiles" />
        </label>
        <span class="muted files">{{ files.map((f) => f.name).join('、') }}</span>
        <button v-if="files.length" class="btn small" @click="files = []">清除</button>
        <span class="spacer" />
        <button class="btn primary" :disabled="creating || (!seed.trim() && !files.length)" @click="create">
          {{ creating ? '创建中…' : '生成蓝图' }}
        </button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <section>
      <h2>我的故事</h2>
      <p v-if="!stories.length" class="muted">还没有故事。</p>
      <div class="list">
        <router-link v-for="s in stories" :key="s.id" :to="`/story/${s.id}`" class="card item">
          <div class="item-head">
            <strong>{{ s.title }}</strong>
            <span class="tag">{{ styleName(s.style_id) }} · {{ statusText(s.status) }}</span>
          </div>
          <p class="muted premise">{{ s.premise }}</p>
          <div class="item-foot muted">
            <span>{{ s.chapter_count }} 章 · {{ s.updated_at.replace('T', ' ') }}</span>
            <button class="btn small danger" @click.prevent="remove(s)">删除</button>
          </div>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import StylePicker from '../components/StylePicker.vue'

const router = useRouter()
const styles = ref([])
const style = ref('realistic')
const styleNotes = ref('')
const seed = ref('')
const files = ref([])
const creating = ref(false)
const error = ref('')
const stories = ref([])

const STATUS = {
  generating: '生成中',
  awaiting_blueprint: '待确认蓝图',
  awaiting_choice: '待选择方向',
  failed: '失败'
}
const statusText = (s) => STATUS[s] || s
const styleName = (id) => styles.value.find((s) => s.id === id)?.name || '写实文学'

const onFiles = (e) => {
  files.value = [...e.target.files]
  e.target.value = ''
}

const load = async () => {
  try {
    ;[stories.value, styles.value] = await Promise.all([api.list(), api.styles()])
  } catch (e) {
    error.value = `无法连接后端：${e.message}`
  }
}

const create = async () => {
  creating.value = true
  error.value = ''
  try {
    const { id } = await api.create(seed.value, files.value, style.value, styleNotes.value)
    router.push(`/story/${id}`)
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

const remove = async (s) => {
  if (!confirm(`删除《${s.title}》？此操作不可恢复。`)) return
  try {
    await api.remove(s.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<style scoped>
.home { max-width: 860px; margin: 0 auto; padding: 48px 16px; display: flex; flex-direction: column; gap: 28px; }
header h1 { font-family: var(--serif); font-size: 30px; }
h2 { font-size: 16px; margin-bottom: 12px; }
.create { display: flex; flex-direction: column; gap: 12px; }
.create h2 { margin: 0; }
.create h3 { font-size: 13px; color: var(--muted); font-weight: 500; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.files { font-size: 12px; }
.spacer { flex: 1; }
.list { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.item { display: flex; flex-direction: column; gap: 6px; transition: border-color .2s; }
.item:hover { border-color: var(--accent); }
.item-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.premise { font-size: 13px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.item-foot { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-top: auto; }
</style>
