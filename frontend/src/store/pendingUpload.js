/**
 * 临时存储待上传的文件和需求
 * 用于首页点击启动引擎后立即跳转，在Process页面再进行API调用
 */
import { reactive } from 'vue'

const STORAGE_KEY = 'mirofish_pending_upload'

function syncToStorage() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      simulationRequirement: state.simulationRequirement,
      isPending: state.isPending
    }))
  } catch {
    // ignore storage errors
  }
}

function restoreFromStorage() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    state.simulationRequirement = parsed.simulationRequirement || ''
    state.isPending = Boolean(parsed.isPending)
  } catch {
    // ignore storage errors
  }
}

const state = reactive({
  files: [],
  simulationRequirement: '',
  isPending: false
})

restoreFromStorage()

export function setPendingUpload(files, requirement) {
  state.files = files
  state.simulationRequirement = requirement
  state.isPending = true
  syncToStorage()
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.isPending = false
  syncToStorage()
}

export default state
