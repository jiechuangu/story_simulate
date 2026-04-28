<template>
  <div class="world-workbench">
    <div v-if="loading" class="state-screen">
      <div class="loading-ring"></div>
      <p>World engine bootstrapping...</p>
    </div>

    <div v-else-if="worldState && roleOnly" class="role-shell">
      <section class="hero-card role-hero">
        <div>
          <div class="eyebrow">Step 6 · Role Control</div>
          <h1>{{ currentRoleName || 'No Role Claimed' }}</h1>
          <p>{{ sceneNarrative }}</p>
        </div>
        <div class="hero-metrics">
          <div class="metric">
            <span class="metric-label">World Time</span>
            <span class="metric-value">{{ formatDateTime(worldState.current_world_time) }}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Current Role</span>
            <span class="metric-value">{{ currentRoleName || 'None' }}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Elapsed</span>
            <span class="metric-value">{{ worldState.elapsed_hours }} h</span>
          </div>
          <div class="metric">
            <span class="metric-label">Facts</span>
            <span class="metric-value">{{ worldState.facts.length }}</span>
          </div>
        </div>
      </section>

      <div class="role-layout">
        <section class="panel role-col-left">
          <div class="panel-header"><h2>World Background</h2></div>
          <p class="summary">{{ worldBackdrop }}</p>

          <div class="panel-header top-space"><h2>Current Plot</h2></div>
          <div class="list">
            <article v-for="event in recentPlotEvents" :key="event.event_id" class="list-card">
              <div class="meta-row">
                <span class="caps">{{ event.event_type }}</span>
                <span>{{ formatDateTime(event.happened_at) }}</span>
              </div>
              <h3>{{ event.title }}</h3>
              <p>{{ event.description }}</p>
            </article>
          </div>

          <div class="panel-header top-space"><h2>Your Objectives</h2></div>
          <div class="list">
            <article v-for="(hint, idx) in objectiveHints" :key="idx" class="list-card">
              <h3>Objective {{ idx + 1 }}</h3>
              <p>{{ hint }}</p>
            </article>
          </div>
        </section>

        <section class="panel role-col-center">
          <div class="panel-header">
            <h2>Scene & Dialogue</h2>
            <span class="muted">{{ selectedCharacter?.name || 'Role not ready' }}</span>
          </div>

          <div class="dialogue-layout role-dialogue" v-if="selectedCharacter">
            <div class="portrait-panel">
              <div class="portrait-frame" v-if="selectedCharacterImageUrl">
                <img :src="selectedCharacterImageUrl" :alt="selectedCharacter.name" />
              </div>
              <div v-else-if="selectedCharacterImageLoading" class="portrait-loading">
                <div class="loading-dot"></div>
                <span>Generating portrait...</span>
              </div>
              <div v-else class="portrait-placeholder">
                {{ selectedCharacter.name.slice(0, 1) }}
              </div>
              <div class="portrait-meta">
                <h3>{{ selectedCharacter.name }}</h3>
                <p>{{ selectedCharacter.profession || selectedCharacter.source_entity_type || 'Character' }}</p>
                <p class="small-text">At {{ selectedCharacter.current_location }}</p>
              </div>
            </div>

            <div class="dialogue-panel">
              <template v-if="roleOnly && selectedActionOption">
                <label>Action Target</label>
                <p class="small-text" v-if="selectedActionOption.type === 'advance'">
                  This action advances time and does not require a dialogue target.
                </p>
                <p class="small-text" v-else-if="selectedActionTargetName">
                  Target is locked by action: <strong>{{ selectedActionTargetName }}</strong>
                </p>
                <p class="small-text" v-else>
                  This action has no explicit target and will be applied as a world action.
                </p>
              </template>
              <template v-else>
                <label>Talk To</label>
                <select v-model="dialogueTargetId">
                  <option disabled value="">Select a character</option>
                  <option v-for="item in dialogueTargets" :key="item.character_id" :value="item.character_id">
                    {{ item.name }}
                  </option>
                </select>
                <p class="small-text">Only reachable characters are listed (same location or current-plot related).</p>
              </template>

              <div class="story-node top-space">
                <template v-if="directorLoading">
                  <h3>Narrative Director</h3>
                  <p>Generating next narrative node...</p>
                </template>
                <template v-else>
                  <h3>{{ storyNodeTitle }}</h3>
                  <p>{{ storyNodeText }}</p>
                  <p v-if="directorError" class="small-text error-text">{{ directorError }}</p>
                  <div class="story-options">
                    <button
                      v-for="option in storyNodeOptions"
                      :key="option.key"
                      class="mini-btn"
                      @click="applyStoryOption(option)"
                    >
                      {{ option.label }}
                    </button>
                  </div>
                </template>
              </div>

              <div class="list chat-list top-space">
                <article v-for="(entry, index) in dialogueHistory" :key="`${entry.target_character_id}-${index}`" class="list-card">
                  <div class="meta-row">
                    <span class="caps">{{ selectedCharacter.name }}</span>
                    <span>{{ entry.target_name }}</span>
                  </div>
                  <p>{{ entry.player_message }}</p>
                  <div class="reply-block">
                    <span class="caps">Reply</span>
                    <p>{{ entry.character_response }}</p>
                  </div>
                  <p v-if="entry.relationship_note" class="small-text">Relationship: {{ entry.relationship_note }}</p>
                  <p v-if="entry.revealed_fact" class="small-text">Revealed: {{ entry.revealed_fact }}</p>
                </article>
              </div>

              <label class="top-space">Action / Dialogue</label>
              <textarea v-model="dialogueInput" rows="4" placeholder="Describe what you do or say in this scene"></textarea>
              <button class="primary-btn top-space" :disabled="isExecutingInteraction" @click="sendDialogue">
                {{ isExecutingInteraction ? 'Executing...' : 'Execute Interaction' }}
              </button>
            </div>
          </div>
        </section>

        <section class="panel role-col-right">
          <div class="panel-header"><h2>Quick Actions</h2></div>
          <div class="quick-grid">
            <button class="ghost-btn" @click="quickAdvanceByHours(12, 'Half Day')">Advance 12h</button>
            <button class="ghost-btn" @click="quickAdvanceByHours(24, 'One Day')">Advance 1d</button>
            <button class="ghost-btn" @click="quickAdvanceByHours(72, 'Three Days')">Advance 3d</button>
          </div>

          <div class="panel-header top-space"><h2>Suggested Moves</h2></div>
          <div class="list">
            <article v-for="(prompt, idx) in quickPrompts" :key="idx" class="list-card">
              <p>{{ prompt }}</p>
              <button class="mini-btn top-space" @click="applyQuickPrompt(prompt)">Use</button>
            </article>
            <article v-if="!quickPrompts.length" class="list-card">
              <p class="small-text">{{ directorLoading ? 'Director is generating suggestions...' : 'No suggested moves yet.' }}</p>
            </article>
          </div>

          <div class="panel-header top-space"><h2>Role State</h2></div>
          <div class="list">
            <article class="list-card">
              <h3>Status</h3>
              <p>{{ selectedCharacter?.status_summary || '-' }}</p>
            </article>
            <article class="list-card">
              <h3>Current Goal</h3>
              <p>{{ selectedCharacter?.current_goal || '-' }}</p>
            </article>
            <article class="list-card">
              <h3>Relations</h3>
              <p v-if="!relationshipLines.length" class="small-text">No explicit relationship notes yet.</p>
              <p v-for="line in relationshipLines" :key="line" class="small-text">{{ line }}</p>
            </article>
          </div>
        </section>
      </div>
    </div>

    <div v-else-if="worldState && !roleOnly" class="grid">
      <section class="hero-card">
        <div>
          <div class="eyebrow">World Engine</div>
          <h1>{{ worldState.world_name }}</h1>
          <p>{{ worldState.simulation_requirement || 'No simulation requirement provided.' }}</p>
        </div>
        <div class="hero-metrics">
          <div class="metric">
            <span class="metric-label">World Time</span>
            <span class="metric-value">{{ formatDateTime(worldState.current_world_time) }}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Elapsed</span>
            <span class="metric-value">{{ worldState.elapsed_hours }} h</span>
          </div>
          <div class="metric">
            <span class="metric-label">Characters</span>
            <span class="metric-value">{{ playableCharacters.length }}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Facts</span>
            <span class="metric-value">{{ worldState.facts.length }}</span>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>Player Control</h2>
          <button v-if="worldState.player_character_id" class="ghost-btn" @click="releaseRole">Release</button>
        </div>
        <p class="small-text">
          Current Role:
          <strong>{{ currentRoleName || 'None' }}</strong>
        </p>

        <label>Player Name</label>
        <input v-model="playerName" type="text" placeholder="Player" />

        <div class="inline-grid top-space">
          <div>
            <label>Advance</label>
            <input v-model.number="advanceAmount" min="1" type="number" />
          </div>
          <div>
            <label>Unit</label>
            <select v-model="advanceUnit">
              <option value="hour">Hour</option>
              <option value="day">Day</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
              <option value="year">Year</option>
            </select>
          </div>
        </div>

        <label class="top-space">Directive</label>
        <textarea v-model="advanceInstruction" rows="3" placeholder="Describe how the world should evolve during this period"></textarea>

        <button class="primary-btn top-space" @click="advanceTime">Advance Timeline</button>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>Inject Fact</h2>
        </div>

        <div class="inline-grid">
          <div>
            <label>Character</label>
            <select v-model="factSubject">
              <option disabled value="">Select character</option>
              <option v-for="character in playableCharacters" :key="character.character_id" :value="character.character_id">
                {{ character.name }}
              </option>
            </select>
          </div>
          <div>
            <label>Predicate</label>
            <input v-model="factPredicate" type="text" placeholder="dislikes / appearance / knows" />
          </div>
        </div>

        <label class="top-space">Object</label>
        <input v-model="factObject" type="text" placeholder="e.g. 香菜 / silver robe / secret prophecy" />

        <label class="top-space">Natural Language</label>
        <textarea v-model="factNaturalLanguage" rows="3" placeholder="e.g. 林黛玉不爱吃香菜"></textarea>

        <label class="top-space">Tags</label>
        <input v-model="factTags" type="text" placeholder="appearance, preference, command" />

        <button class="primary-btn top-space" @click="injectFact">Inject Into World</button>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>Timeline</h2>
          <button class="ghost-btn small" @click="timelineMode = timelineMode === 'selected' ? 'all' : 'selected'">
            {{ timelineMode === 'selected' ? 'Show All' : 'Focus Selected' }}
          </button>
        </div>
        <div class="list">
          <article v-for="event in filteredTimeline" :key="event.event_id" class="list-card">
            <div class="meta-row">
              <span class="caps">{{ event.event_type }}</span>
              <span>{{ formatDateTime(event.happened_at) }}</span>
            </div>
            <h3>{{ event.title }}</h3>
            <p>{{ event.description }}</p>
          </article>
        </div>
      </section>

      <section v-if="!roleOnly" class="panel span-two">
        <div class="panel-header">
          <h2>Characters</h2>
          <span class="muted">{{ worldState.player_character_id ? 'One role currently occupied' : 'Only Character entities are playable' }}</span>
        </div>
        <div class="character-grid">
          <article
            v-for="character in playableCharacters"
            :key="character.character_id"
            class="character-card"
            :class="{ active: selectedCharacterId === character.character_id, claimed: character.is_player_controlled }"
            @click="selectedCharacterId = character.character_id"
          >
            <div class="character-head">
              <div>
                <h3>{{ character.name }}</h3>
                <p>{{ character.profession || character.source_entity_type || 'Character' }}</p>
              </div>
              <button class="mini-btn" @click.stop="claimRole(character.character_id)">
                {{ character.is_player_controlled ? 'Playing' : 'Play' }}
              </button>
            </div>

            <p class="summary">{{ character.summary || character.persona }}</p>
            <p class="summary small-text">At {{ character.current_location }} · Goal: {{ character.current_goal }}</p>

            <div v-if="character.appearance_notes.length" class="tag-row">
              <span v-for="note in character.appearance_notes.slice(0, 3)" :key="note" class="tag">{{ note }}</span>
            </div>

            <div class="card-actions">
              <button class="ghost-btn small" @click.stop="generateImage(character.character_id)">Generate Art</button>
            </div>
          </article>
        </div>
      </section>

      <section class="panel span-two">
        <div class="panel-header">
          <h2>Dialogue</h2>
          <span class="muted">{{ selectedCharacter?.name || 'Select a character to start a scene' }}</span>
        </div>
        <div class="dialogue-layout" v-if="selectedCharacter">
          <div class="portrait-panel">
            <div class="portrait-frame" v-if="selectedCharacterImageUrl">
              <img :src="selectedCharacterImageUrl" :alt="selectedCharacter.name" />
            </div>
            <div v-else-if="selectedCharacterImageLoading" class="portrait-loading">
              <div class="loading-dot"></div>
              <span>Generating portrait...</span>
            </div>
            <div v-else class="portrait-placeholder">
              {{ selectedCharacter.name.slice(0, 1) }}
            </div>
            <div class="portrait-meta">
              <h3>{{ selectedCharacter.name }}</h3>
              <p>{{ selectedCharacter.profession || selectedCharacter.source_entity_type || 'Character' }}</p>
              <p class="small-text">At {{ selectedCharacter.current_location }}</p>
            </div>
          </div>

          <div class="dialogue-panel">
            <div class="list chat-list">
              <article v-for="(entry, index) in dialogueHistory" :key="`${entry.target_character_id}-${index}`" class="list-card">
                <div class="meta-row">
                  <span class="caps">Player</span>
                  <span>{{ entry.target_name }}</span>
                </div>
                <p>{{ entry.player_message }}</p>
                <div class="reply-block">
                  <span class="caps">Reply</span>
                  <p>{{ entry.character_response }}</p>
                </div>
                <p v-if="entry.revealed_fact" class="small-text">Revealed: {{ entry.revealed_fact }}</p>
              </article>
            </div>

            <label class="top-space">Speak As Player</label>
            <textarea v-model="dialogueInput" rows="4" placeholder="Say something that might change this character's direction"></textarea>
            <button class="primary-btn top-space" :disabled="isExecutingInteraction" @click="sendDialogue">
              {{ isExecutingInteraction ? 'Sending...' : 'Send Dialogue' }}
            </button>
          </div>
        </div>
      </section>

      <section class="panel span-two">
        <div class="panel-header">
          <h2>Image Tasks</h2>
          <input v-model="imageModel" class="model-input" type="text" placeholder="x/flux2-klein:4b-fp8" />
        </div>
        <div class="list">
          <article v-for="task in imageTasks.slice(0, 10)" :key="task.task_id" class="list-card">
            <div class="meta-row">
              <span class="caps">{{ task.task_id }}</span>
              <span :class="['status-badge', task.status]">{{ task.status }}</span>
            </div>
            <h3>{{ task.model }}</h3>
            <p>{{ task.prompt }}</p>
            <p v-if="task.output_path" class="output-path">{{ task.output_path }}</p>
            <p v-if="task.error" class="error-text">{{ task.error }}</p>
          </article>
        </div>
      </section>
    </div>

    <div v-else class="state-screen">
      <p>No world state available.</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import {
  addWorldFact,
  advanceWorldTime,
  bootstrapWorld,
  claimWorldCharacter,
  createWorldImageTask,
  fetchDirectorNode,
  getWorldState,
  listWorldImageTasks,
  processWorldDialogue,
  releaseWorldCharacter
} from '../api/world'

const props = defineProps({
  simulationId: String,
  roleOnly: {
    type: Boolean,
    default: false
  },
  lockedCharacterId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['add-log', 'update-status'])

const loading = ref(false)
const worldState = ref(null)
const imageTasks = ref([])
const selectedCharacterId = ref('')
const playerName = ref('Player')
const advanceAmount = ref(1)
const advanceUnit = ref('day')
const advanceInstruction = ref('')
const factSubject = ref('')
const factPredicate = ref('dislikes')
const factObject = ref('')
const factNaturalLanguage = ref('')
const factTags = ref('')
const imageModel = ref('x/flux2-klein:4b-fp8')
const timelineMode = ref('all')
const dialogueInput = ref('')
const dialogueTargetId = ref('')
const dialogueHistory = ref([])
const isExecutingInteraction = ref(false)
const selectedActionOption = ref(null)
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'
const claimInProgress = ref(false)
const imageGeneratingFor = ref('')
const autoPortraitRequested = ref(new Set())
const narrativeStepCounter = ref(0)
const directorNode = ref(null)
const directorLoading = ref(false)
const directorError = ref('')

const log = (message) => emit('add-log', message)

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
  const nonCharacter = nonCharacterKeywords.some((kw) => name.includes(kw))
  return nonCharacter ? 'faction' : 'character'
}

const isPlayableCharacter = (character) => {
  const t = inferEntityType(character)
  return t === 'character' || t === 'person' || t === 'human'
}

const syncState = (state) => {
  worldState.value = state
  const playable = (state.characters || []).filter(isPlayableCharacter)
  if (props.roleOnly && props.lockedCharacterId) {
    const exists = playable.some(c => c.character_id === props.lockedCharacterId)
    selectedCharacterId.value = exists ? props.lockedCharacterId : (playable[0]?.character_id || '')
  } else if (!selectedCharacterId.value && playable.length) {
    selectedCharacterId.value = playable[0].character_id
  } else if (selectedCharacterId.value && !playable.some(c => c.character_id === selectedCharacterId.value)) {
    selectedCharacterId.value = playable[0]?.character_id || ''
  }
  if (!factSubject.value && playable.length) {
    factSubject.value = playable[0].character_id
  } else if (factSubject.value && !playable.some(c => c.character_id === factSubject.value)) {
    factSubject.value = playable[0]?.character_id || ''
  }
  if (props.roleOnly) {
    const candidates = playable.filter(c => c.character_id !== selectedCharacterId.value)
    if (!dialogueTargetId.value && candidates.length) {
      dialogueTargetId.value = candidates[0].character_id
    } else if (dialogueTargetId.value && !candidates.some(c => c.character_id === dialogueTargetId.value)) {
      dialogueTargetId.value = candidates[0]?.character_id || ''
    }
  }
}

const ensureLockedCharacterClaimed = async () => {
  if (!props.roleOnly || !props.lockedCharacterId || !worldState.value || claimInProgress.value) return
  const candidate = playableCharacters.value.find(item => item.character_id === props.lockedCharacterId)
  if (!candidate) {
    log(`Locked role not playable: ${props.lockedCharacterId}`)
    return
  }
  if (worldState.value.player_character_id === props.lockedCharacterId) return
  claimInProgress.value = true
  try {
    await claimRole(props.lockedCharacterId)
  } finally {
    claimInProgress.value = false
  }
}

const loadWorld = async () => {
  if (!props.simulationId) return
  loading.value = true
  emit('update-status', 'processing')
  try {
    const bootstrap = await bootstrapWorld({ simulation_id: props.simulationId })
    syncState(bootstrap.data)
    await ensureLockedCharacterClaimed()
    const tasks = await listWorldImageTasks(props.simulationId)
    imageTasks.value = tasks.data || []
    await refreshDirectorNode()
    emit('update-status', 'completed')
    log(`World engine ready for simulation ${props.simulationId}`)
  } catch (error) {
    emit('update-status', 'error')
    log(`World bootstrap failed: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const refreshWorld = async () => {
  if (!props.simulationId) return
  const state = await getWorldState(props.simulationId)
  syncState(state.data)
  const tasks = await listWorldImageTasks(props.simulationId)
  imageTasks.value = tasks.data || []
  await refreshDirectorNode()
}

const refreshDirectorNode = async () => {
  if (!props.roleOnly || !props.simulationId || !selectedCharacterId.value) return
  directorLoading.value = true
  directorError.value = ''
  try {
    const res = await fetchDirectorNode(props.simulationId, {
      character_id: selectedCharacterId.value,
      target_character_id: dialogueTargetId.value || '',
      narrative_step: narrativeStepCounter.value
    })
    directorNode.value = res.data || null
    selectedActionOption.value = null
    if (typeof res.data?.narrative_step === 'number') {
      narrativeStepCounter.value = res.data.narrative_step
    }
    if (Array.isArray(res.data?.dialogue_targets) && res.data.dialogue_targets.length) {
      const ids = res.data.dialogue_targets.map(item => item.character_id)
      if (!dialogueTargetId.value || !ids.includes(dialogueTargetId.value)) {
        dialogueTargetId.value = res.data.dialogue_targets[0].character_id
      }
    }
  } catch (error) {
    directorError.value = error.message || 'Director node generation failed'
    log(`Narrative director failed: ${directorError.value}`)
  } finally {
    directorLoading.value = false
  }
}

const claimRole = async (characterId) => {
  const candidate = playableCharacters.value.find(item => item.character_id === characterId)
  if (!candidate) {
    log('Only Character entities can be played')
    return
  }
  try {
    const res = await claimWorldCharacter(props.simulationId, {
      character_id: characterId,
      player_name: playerName.value || 'Player'
    })
    syncState(res.data)
    log(`Player claimed role ${characterId}`)
  } catch (error) {
    log(`Claim role failed: ${error.message}`)
  }
}

const releaseRole = async () => {
  try {
    const res = await releaseWorldCharacter(props.simulationId)
    syncState(res.data)
    log('Released current role')
  } catch (error) {
    log(`Release role failed: ${error.message}`)
  }
}

const advanceTime = async () => {
  try {
    const res = await advanceWorldTime(props.simulationId, {
      amount: advanceAmount.value,
      unit: advanceUnit.value,
      narrative_instruction: advanceInstruction.value
    })
    syncState(res.data)
    log(`Advanced world by ${advanceAmount.value} ${advanceUnit.value}`)
  } catch (error) {
    log(`Advance time failed: ${error.message}`)
  }
}

const injectFact = async () => {
  if (!factSubject.value || !factPredicate.value || !factObject.value) {
    log('Fact injection requires character, predicate and object')
    return
  }
  try {
    const res = await addWorldFact(props.simulationId, {
      scope: 'character',
      subject: factSubject.value,
      predicate: factPredicate.value,
      object_value: factObject.value,
      natural_language: factNaturalLanguage.value || `${factSubject.value} ${factPredicate.value} ${factObject.value}`,
      tags: factTags.value.split(',').map(item => item.trim()).filter(Boolean)
    })
    syncState(res.data)
    factObject.value = ''
    factNaturalLanguage.value = ''
    log(`Injected fact into ${factSubject.value}`)
  } catch (error) {
    log(`Inject fact failed: ${error.message}`)
  }
}

const generateImage = async (characterId) => {
  imageGeneratingFor.value = characterId
  try {
    const res = await createWorldImageTask(props.simulationId, {
      character_id: characterId,
      model: imageModel.value,
      auto_generate: true
    })
    imageTasks.value = [res.data, ...imageTasks.value]
    log(`Started image generation for ${characterId}`)
    await refreshWorld()
  } catch (error) {
    log(`Image generation failed: ${error.message}`)
  } finally {
    if (imageGeneratingFor.value === characterId) {
      imageGeneratingFor.value = ''
    }
  }
}

const formatDateTime = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

const selectedCharacter = computed(() => {
  if (!worldState.value || !selectedCharacterId.value) return null
  return playableCharacters.value.find(item => item.character_id === selectedCharacterId.value) || null
})

const currentRoleName = computed(() => {
  if (!worldState.value?.player_character_id) return ''
  const found = (worldState.value.characters || []).find(item => item.character_id === worldState.value.player_character_id)
  return found?.name || worldState.value.player_character_id
})

const playableCharacters = computed(() => {
  if (!worldState.value) return []
  return (worldState.value.characters || []).filter(isPlayableCharacter)
})

const selectedCharacterImageTask = computed(() => {
  if (!selectedCharacter.value?.latest_image_task_id) return null
  const allTasks = [
    ...(imageTasks.value || []),
    ...((worldState.value?.image_tasks || []).filter(Boolean))
  ]
  return allTasks.find(task => task.task_id === selectedCharacter.value.latest_image_task_id) || null
})

const selectedCharacterImageLoading = computed(() => {
  if (!selectedCharacter.value) return false
  if (imageGeneratingFor.value === selectedCharacter.value.character_id) return true
  const status = (selectedCharacterImageTask.value?.status || '').toLowerCase()
  return ['queued', 'running', 'pending'].includes(status)
})

const selectedCharacterImageUrl = computed(() => {
  if (!props.simulationId || !selectedCharacter.value?.latest_image_task_id) return ''
  const status = (selectedCharacterImageTask.value?.status || '').toLowerCase()
  if (status && status !== 'completed') return ''
  return `${apiBaseUrl}/api/world/${props.simulationId}/image-tasks/${selectedCharacter.value.latest_image_task_id}/file`
})

const filteredTimeline = computed(() => {
  if (!worldState.value) return []
  if (timelineMode.value !== 'selected' || !selectedCharacterId.value) {
    return worldState.value.timeline_events.slice(0, 12)
  }
  return worldState.value.timeline_events
    .filter(event => (event.related_character_ids || []).includes(selectedCharacterId.value))
    .slice(0, 12)
})

const dialogueTargets = computed(() => {
  if (!playableCharacters.value.length) return []
  if (!props.roleOnly) return playableCharacters.value
  if (Array.isArray(directorNode.value?.dialogue_targets) && directorNode.value.dialogue_targets.length) {
    const allowed = new Set(directorNode.value.dialogue_targets.map(item => item.character_id))
    return playableCharacters.value.filter(item => allowed.has(item.character_id))
  }
  return playableCharacters.value.filter(item => item.character_id !== selectedCharacterId.value).slice(0, 8)
})

const worldBackdrop = computed(() => {
  const base = (worldState.value?.simulation_requirement || '').trim()
  if (base) return base
  return 'No explicit world requirement provided.'
})

const recentPlotEvents = computed(() => {
  const events = worldState.value?.timeline_events || []
  return events.slice(0, 5)
})

const objectiveHints = computed(() => {
  if (props.roleOnly && Array.isArray(directorNode.value?.objectives) && directorNode.value.objectives.length) {
    return directorNode.value.objectives.slice(0, 4)
  }
  if (!selectedCharacter.value) return ['Claim a role and begin interacting with the world.']
  const topics = (selectedCharacter.value.interested_topics || []).slice(0, 2)
  const hints = [
    `Pursue current goal: ${selectedCharacter.value.current_goal || 'observe the world'}.`,
    `Visit ${selectedCharacter.value.current_location || 'a meaningful location'} and create a new interaction.`,
  ]
  if (topics.length) {
    hints.push(`Explore topic tension around: ${topics.join(' / ')}.`)
  }
  return hints
})

const sceneNarrative = computed(() => {
  const role = selectedCharacter.value
  const latest = recentPlotEvents.value[0]
  if (!role) return 'Select a role and enter the world scene.'
  const eventLine = latest ? `Latest event: ${latest.title}.` : 'The world is waiting for your move.'
  return `${role.name} is currently at ${role.current_location}. Goal: ${role.current_goal}. ${eventLine}`
})

const quickPrompts = computed(() => {
  if (!props.roleOnly) return []
  return (directorNode.value?.suggested_moves || []).slice(0, 3)
})

const storyNodeTitle = computed(() => {
  if (!props.roleOnly) return `Narrative Node ${narrativeStepCounter.value + 1}`
  return directorNode.value?.node_title || `Narrative Node ${narrativeStepCounter.value + 1}`
})

const storyNodeText = computed(() => {
  if (!selectedCharacter.value) return 'Select a role to enter the story flow.'
  if (!props.roleOnly) return 'Choose one branch to continue the scene.'
  return directorNode.value?.node_text || 'Narrative director is preparing the current node.'
})

const storyNodeOptions = computed(() => {
  if (!props.roleOnly) return []
  const options = directorNode.value?.node_options || []
  return options.map(option => ({
    ...option,
    targetId: option.targetId || option.target_id || ''
  }))
})

const selectedActionTargetName = computed(() => {
  const targetId = selectedActionOption.value?.targetId || selectedActionOption.value?.target_id || ''
  if (!targetId) return ''
  const hit = dialogueTargets.value.find(item => item.character_id === targetId)
  return hit?.name || targetId
})

const relationshipLines = computed(() => {
  const notes = selectedCharacter.value?.relationship_notes || {}
  return Object.entries(notes).slice(0, 6).map(([k, v]) => `${k}: ${v}`)
})

const sendDialogue = async () => {
  if (isExecutingInteraction.value) return
  if (!selectedCharacter.value || !dialogueInput.value.trim()) {
    log('Dialogue requires a selected character and a non-empty message')
    return
  }
  const action = selectedActionOption.value
  const actionTargetId = action?.targetId || action?.target_id || ''
  const targetCharacterId = props.roleOnly
    ? (action ? actionTargetId : dialogueTargetId.value)
    : selectedCharacter.value.character_id
  isExecutingInteraction.value = true
  try {
    if (props.roleOnly && action && !actionTargetId) {
      const res = await advanceWorldTime(props.simulationId, {
        amount: 1,
        unit: 'hour',
        narrative_instruction: dialogueInput.value.trim()
      })
      syncState(res.data)
      dialogueInput.value = ''
      narrativeStepCounter.value += 1
      selectedActionOption.value = null
      refreshDirectorNode().catch(() => {})
      log('Action executed without direct dialogue target')
    } else {
      if (!targetCharacterId) {
        log('Please select an action or dialogue target first')
        return
      }
      const res = await processWorldDialogue(props.simulationId, {
        target_character_id: targetCharacterId,
        message: dialogueInput.value.trim()
      })
      syncState(res.data.world_state)
      dialogueHistory.value.unshift(res.data.dialogue)
      dialogueInput.value = ''
      narrativeStepCounter.value += 1
      selectedActionOption.value = null
      refreshDirectorNode().catch(() => {})
      log(`Dialogue updated ${res.data.dialogue.target_name}'s world state`)
    }
  } catch (error) {
    log(`Dialogue failed: ${error.message}`)
  } finally {
    isExecutingInteraction.value = false
  }
}

const quickAdvanceByHours = async (hours, label) => {
  try {
    const res = await advanceWorldTime(props.simulationId, {
      amount: hours,
      unit: 'hour',
      narrative_instruction: `Quick action: ${label}`
    })
    syncState(res.data)
    narrativeStepCounter.value += 1
    refreshDirectorNode().catch(() => {})
    log(`Advanced world by ${hours}h`)
  } catch (error) {
    log(`Quick advance failed: ${error.message}`)
  }
}

const inferTargetIdFromText = (text) => {
  const value = (text || '').trim()
  if (!value) return ''
  for (const item of dialogueTargets.value || []) {
    const full = item.name || ''
    const base = full.split('_')[0] || full
    if ((full && value.includes(full)) || (base && value.includes(base))) {
      return item.character_id
    }
  }
  return ''
}

const applyQuickPrompt = (prompt) => {
  const targetId = inferTargetIdFromText(prompt)
  selectedActionOption.value = {
    key: `quick_${Date.now()}`,
    type: 'prompt',
    label: 'Suggested Move',
    prompt,
    targetId
  }
  if (targetId) {
    dialogueTargetId.value = targetId
  }
  dialogueInput.value = prompt
}

const applyStoryOption = async (option) => {
  if (!option) return
  if (option.type === 'advance') {
    selectedActionOption.value = { ...option }
    await quickAdvanceByHours(option.hours || 12, option.caption || 'Narrative branch')
    return
  }
  const targetId = option.targetId || option.target_id || ''
  selectedActionOption.value = { ...option, targetId }
  if (targetId) {
    dialogueTargetId.value = targetId
  }
  if (option.prompt) {
    dialogueInput.value = option.prompt
  }
}

const ensureSelectedCharacterPortrait = async () => {
  if (!props.roleOnly || !selectedCharacter.value) return
  const characterId = selectedCharacter.value.character_id
  if (selectedCharacter.value.latest_image_task_id) return
  if (autoPortraitRequested.value.has(characterId)) return
  autoPortraitRequested.value.add(characterId)
  await generateImage(characterId)
}

watch(() => props.simulationId, loadWorld, { immediate: true })
watch(() => props.lockedCharacterId, async () => {
  await refreshWorld()
  await ensureLockedCharacterClaimed()
  await ensureSelectedCharacterPortrait()
})
watch(() => selectedCharacterId.value, async () => {
  await ensureSelectedCharacterPortrait()
  await refreshDirectorNode()
})
watch(() => dialogueTargetId.value, async () => {
  await refreshDirectorNode()
})
</script>

<style scoped>
.world-workbench {
  height: 100%;
  overflow: auto;
  padding: 24px;
  background: linear-gradient(180deg, #f5f1e8 0%, #ede5d8 100%);
  color: #241f18;
}

.state-screen {
  height: 100%;
  display: grid;
  place-items: center;
  color: #6c6255;
}

.loading-ring {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(36, 31, 24, 0.12);
  border-top-color: #8b5e3c;
  border-radius: 999px;
  animation: spin 1s linear infinite;
  margin: 0 auto 12px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.role-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.role-layout {
  display: grid;
  grid-template-columns: 1.1fr 1.4fr 1fr;
  gap: 16px;
}

.role-col-left,
.role-col-center,
.role-col-right {
  min-height: 0;
}

.role-col-left .list,
.role-col-right .list {
  max-height: 260px;
  overflow: auto;
}

.role-col-center .chat-list {
  max-height: 320px;
}

.role-dialogue {
  grid-template-columns: 240px 1fr;
}

.quick-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.story-node {
  border: 1px solid #ebdfcf;
  border-radius: 12px;
  background: #fffdf8;
  padding: 10px 12px;
}

.story-node h3 {
  margin: 0 0 6px;
  font-size: 14px;
}

.story-node p {
  margin: 0;
  color: #5f564c;
  font-size: 13px;
  line-height: 1.5;
}

.story-options {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hero-card,
.panel {
  background: rgba(255, 251, 244, 0.9);
  border: 1px solid rgba(82, 67, 47, 0.12);
  border-radius: 20px;
  box-shadow: 0 16px 40px rgba(61, 47, 29, 0.08);
}

.hero-card {
  grid-column: 1 / -1;
  padding: 24px;
  display: flex;
  justify-content: space-between;
  gap: 24px;
}

.eyebrow,
.caps,
label {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 12px;
  color: #8b5e3c;
}

.hero-card h1,
.panel h2,
.list-card h3,
.character-card h3 {
  margin: 0;
}

.hero-card p,
.summary,
.list-card p,
.character-card p {
  color: #5f564c;
}

.hero-metrics {
  min-width: 320px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.metric {
  padding: 12px 14px;
  border-radius: 14px;
  background: #f2eadc;
}

.metric-label,
.muted,
.meta-row {
  font-size: 12px;
  color: #7a7064;
}

.metric-value {
  display: block;
  margin-top: 4px;
  font-weight: 700;
}

.panel {
  padding: 18px;
}

.span-two {
  grid-column: 1 / -1;
}

.panel-header,
.meta-row,
.character-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

input,
select,
textarea {
  width: 100%;
  box-sizing: border-box;
  margin-top: 8px;
  border: 1px solid #d8cbba;
  border-radius: 12px;
  padding: 10px 12px;
  background: #fffdf8;
  font: inherit;
}

.inline-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.top-space {
  margin-top: 14px;
}

.primary-btn,
.ghost-btn,
.mini-btn {
  border: 0;
  border-radius: 999px;
  cursor: pointer;
  font: inherit;
}

.primary-btn {
  background: #214b43;
  color: #fff;
  padding: 11px 16px;
}

.ghost-btn,
.mini-btn {
  background: #eee1ce;
  color: #4e4438;
  padding: 8px 12px;
}

.small {
  font-size: 12px;
}

.list,
.character-grid {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.character-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.list-card,
.character-card {
  border: 1px solid #ebdfcf;
  border-radius: 16px;
  padding: 14px;
  background: #fffdf9;
}

.character-card.active {
  border-color: #214b43;
}

.character-card.claimed {
  background: #eef7f3;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.tag {
  font-size: 12px;
  background: #f5ecdd;
  color: #8b5e3c;
  border-radius: 999px;
  padding: 5px 10px;
}

.card-actions,
.output-path,
.error-text {
  margin-top: 12px;
}

.status-badge.completed {
  color: #117b53;
}

.status-badge.failed,
.error-text {
  color: #b42318;
}

.status-badge.running,
.status-badge.queued {
  color: #8b5e3c;
}

.model-input {
  margin-top: 0;
  min-width: 240px;
}

.dialogue-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  margin-top: 14px;
}

.portrait-panel,
.portrait-frame,
.portrait-placeholder,
.reply-block {
  border-radius: 16px;
}

.portrait-panel {
  background: #fffdf8;
  border: 1px solid #ebdfcf;
  padding: 14px;
}

.portrait-frame {
  overflow: hidden;
  background: #f2eadc;
  aspect-ratio: 4 / 5;
}

.portrait-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.portrait-placeholder {
  display: grid;
  place-items: center;
  aspect-ratio: 4 / 5;
  background: linear-gradient(180deg, #ceb293 0%, #8b5e3c 100%);
  color: #fff;
  font-size: 72px;
  font-weight: 700;
}

.portrait-loading {
  display: grid;
  place-items: center;
  gap: 10px;
  aspect-ratio: 4 / 5;
  background: #f2eadc;
  color: #6c6255;
  border-radius: 16px;
  font-size: 13px;
}

.loading-dot {
  width: 26px;
  height: 26px;
  border: 3px solid rgba(36, 31, 24, 0.14);
  border-top-color: #8b5e3c;
  border-radius: 999px;
  animation: spin 1s linear infinite;
}

.portrait-meta {
  margin-top: 12px;
}

.chat-list {
  max-height: 360px;
  overflow: auto;
}

.reply-block {
  margin-top: 10px;
  background: #f4ede2;
  padding: 12px;
}

.small-text {
  font-size: 12px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .role-layout,
  .grid,
  .character-grid,
  .inline-grid {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
  }

  .hero-metrics {
    min-width: 0;
  }

  .dialogue-layout {
    grid-template-columns: 1fr;
  }
}
</style>
