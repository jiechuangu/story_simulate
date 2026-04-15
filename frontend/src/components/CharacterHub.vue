<template>
  <div class="hub">
    <section class="hero">
      <div>
        <div class="eyebrow">Step 5</div>
        <h2>Character Hub</h2>
        <p>Select a playable character, then enter Role Control (Step 6).</p>
      </div>
      <div class="stats">
        <div class="stat">
          <span class="label">Playable</span>
          <span class="value">{{ filteredCharacters.length }}</span>
        </div>
        <div class="stat">
          <span class="label">World Time</span>
          <span class="value">{{ formatDateTime(worldState?.current_world_time) }}</span>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h3>Add Character</h3>
        <button class="ghost-btn" @click="showAdd = !showAdd">{{ showAdd ? 'Close' : 'Add Character' }}</button>
      </div>
      <div v-if="showAdd" class="form-grid">
        <input v-model="newCharacter.name" placeholder="Character name" />
        <input v-model="newCharacter.profession" placeholder="Profession (optional)" />
        <input v-model="newCharacter.current_location" placeholder="Current location (optional)" />
        <input v-model="newCharacter.current_goal" placeholder="Current goal (optional)" />
        <textarea v-model="newCharacter.summary" rows="2" placeholder="Summary"></textarea>
        <textarea v-model="newCharacter.persona" rows="3" placeholder="Persona"></textarea>
        <input v-model="newAppearance" placeholder="Appearance notes, comma separated (optional)" />
        <button class="primary-btn" :disabled="adding" @click="addCharacter">{{ adding ? 'Adding...' : 'Create Character' }}</button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h3>Playable Characters</h3>
        <input v-model="query" class="search" placeholder="Search by name..." />
      </div>
      <div v-if="loading" class="empty">Loading characters...</div>
      <div v-else-if="filteredCharacters.length === 0" class="empty">No playable characters found.</div>
      <div v-else class="grid">
        <article v-for="character in filteredCharacters" :key="character.character_id" class="card" @click="openRoleControl(character.character_id)">
          <div class="top">
            <h4>{{ character.name }}</h4>
            <span class="chip">Character</span>
          </div>
          <p class="summary">{{ character.summary || character.persona }}</p>
          <p class="meta">{{ character.current_location }} · {{ character.current_goal }}</p>
          <div class="actions">
            <button class="primary-btn">Play</button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { bootstrapWorld, createWorldCharacter } from '../api/world'

const props = defineProps({
  simulationId: String,
  reportId: String
})

const emit = defineEmits(['add-log', 'update-status'])
const router = useRouter()

const loading = ref(false)
const adding = ref(false)
const showAdd = ref(false)
const worldState = ref(null)
const query = ref('')
const newAppearance = ref('')
const newCharacter = ref({
  name: '',
  profession: '',
  current_location: '',
  current_goal: '',
  summary: '',
  persona: ''
})

const log = (msg) => emit('add-log', msg)

const inferEntityType = (character) => {
  const raw = (character?.source_entity_type || '').toLowerCase().trim()
  if (raw === 'people') return 'person'
  if (raw === '人物' || raw === '角色') return 'character'
  if (raw) return raw
  const name = character?.name || ''
  const nonCharacterKeywords = [
    '学院', '宗', '门', '殿', '塔', '森林', '酒店', '村', '帝国', '王国', '组织', '势力', '机构', '总部', '联盟',
    'academy', 'sect', 'clan', 'hall', 'temple', 'forest', 'village', 'kingdom', 'empire', 'organization', 'faction'
  ]
  return nonCharacterKeywords.some((kw) => name.includes(kw)) ? 'faction' : 'character'
}

const isPlayableCharacter = (character) => {
  const t = inferEntityType(character)
  return t === 'character' || t === 'person' || t === 'human'
}

const playableCharacters = computed(() => {
  if (!worldState.value) return []
  return (worldState.value.characters || []).filter(isPlayableCharacter)
})

const filteredCharacters = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return playableCharacters.value
  return playableCharacters.value.filter((c) => (c.name || '').toLowerCase().includes(q))
})

const loadWorld = async () => {
  if (!props.simulationId) return
  loading.value = true
  emit('update-status', 'processing')
  try {
    const res = await bootstrapWorld({ simulation_id: props.simulationId })
    worldState.value = res.data
    emit('update-status', 'completed')
  } catch (error) {
    emit('update-status', 'error')
    log(`Load world failed: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const openRoleControl = (characterId) => {
  router.push({ name: 'RoleIntro', params: { reportId: props.reportId, characterId } })
}

const addCharacter = async () => {
  if (!props.simulationId || !newCharacter.value.name.trim()) {
    log('Character name is required')
    return
  }
  adding.value = true
  try {
    const payload = {
      ...newCharacter.value,
      appearance_notes: newAppearance.value.split(',').map(x => x.trim()).filter(Boolean)
    }
    const res = await createWorldCharacter(props.simulationId, payload)
    worldState.value = res.data
    log(`Character created: ${newCharacter.value.name}`)
    const created = (worldState.value.characters || []).slice().reverse().find(c => c.name === newCharacter.value.name)
    newCharacter.value = { name: '', profession: '', current_location: '', current_goal: '', summary: '', persona: '' }
    newAppearance.value = ''
    showAdd.value = false
    if (created?.character_id) {
      openRoleControl(created.character_id)
    }
  } catch (error) {
    log(`Create character failed: ${error.message}`)
  } finally {
    adding.value = false
  }
}

const formatDateTime = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

watch(() => props.simulationId, loadWorld, { immediate: true })
</script>

<style scoped>
.hub { height: 100%; overflow: auto; padding: 20px; background: #f7f3ea; color: #231f1a; }
.hero, .panel { background: #fffaf0; border: 1px solid #e9decd; border-radius: 16px; padding: 16px; margin-bottom: 14px; }
.hero { display: flex; justify-content: space-between; gap: 16px; }
.eyebrow { font-size: 12px; text-transform: uppercase; letter-spacing: .12em; color: #8b5e3c; }
.hero h2 { margin: 6px 0 8px; }
.hero p { margin: 0; color: #6d6358; }
.stats { display: flex; gap: 10px; }
.stat { background: #f2e8d8; border-radius: 12px; padding: 10px 12px; min-width: 120px; }
.label { display: block; font-size: 11px; color: #7a7064; text-transform: uppercase; }
.value { display: block; margin-top: 6px; font-weight: 700; }
.panel-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
.panel-header h3 { margin: 0; }
.search { max-width: 280px; }
.form-grid { display: grid; gap: 10px; }
input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #d8cbba; border-radius: 10px; padding: 10px 12px; background: #fffdf8; font: inherit; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.card { border: 1px solid #eadfce; border-radius: 14px; background: #fffdf8; padding: 12px; cursor: pointer; }
.card:hover { border-color: #214b43; }
.top { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.top h4 { margin: 0; }
.chip { font-size: 11px; color: #6b5f53; background: #efe4d3; border-radius: 999px; padding: 3px 8px; }
.summary { color: #5f564c; font-size: 13px; min-height: 36px; }
.meta { color: #7a7064; font-size: 12px; }
.actions { margin-top: 8px; }
.primary-btn, .ghost-btn { border: 0; border-radius: 999px; cursor: pointer; font: inherit; }
.primary-btn { background: #214b43; color: white; padding: 9px 12px; }
.ghost-btn { background: #eee1ce; color: #4e4438; padding: 7px 10px; }
.empty { color: #7a7064; font-size: 13px; }
@media (max-width: 960px) { .grid { grid-template-columns: 1fr; } .hero { flex-direction: column; } }
</style>
