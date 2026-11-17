<template>
  <div class="picker">
    <div class="grid">
      <button
        v-for="s in styles"
        :key="s.id"
        type="button"
        class="opt"
        :class="{ on: s.id === modelValue }"
        :disabled="disabled"
        @click="$emit('update:modelValue', s.id)"
      >
        <strong>{{ s.name }}</strong>
        <span class="muted">{{ s.tagline }}</span>
        <span v-if="s.examples.length" class="ex">{{ s.examples.join(' · ') }}</span>
      </button>
    </div>
    <input
      type="text"
      :value="notes"
      :disabled="disabled"
      placeholder="可选：补充你自己的文风要求，例如“第一人称”“多用短句”“模仿武侠小说的腔调”“少写血腥”"
      @input="$emit('update:notes', $event.target.value)"
    />
  </div>
</template>

<script setup>
defineProps({
  styles: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
  notes: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})
defineEmits(['update:modelValue', 'update:notes'])
</script>

<style scoped>
.picker { display: flex; flex-direction: column; gap: 10px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px; }
.opt {
  text-align: left; display: flex; flex-direction: column; gap: 3px; padding: 10px 12px;
  border: 1px solid var(--line); border-radius: 8px; background: #fff; cursor: pointer; font: inherit; color: inherit;
}
.opt span { font-size: 12px; }
.opt .ex { color: var(--accent); opacity: .8; }
.opt:hover:not(:disabled) { border-color: var(--accent); }
.opt.on { border-color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent); }
.opt:disabled { cursor: not-allowed; opacity: .6; }
</style>
