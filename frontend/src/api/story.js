import service, { requestWithRetry } from './index'

export const createStorySession = (data) => {
  return requestWithRetry(() => service.post('/api/story/generate', data), 3, 1000)
}

export const createStorySessionFromSeed = (data) => {
  return requestWithRetry(() => service.post('/api/story/generate-from-seed', data), 3, 1000)
}

export const getStorySessionStatus = (storyId) => {
  return service.post('/api/story/generate/status', { report_id: storyId })
}

export const getStoryLogs = (storyId, fromLine = 0) => {
  return service.get(`/api/story/${storyId}/agent-log`, { params: { from_line: fromLine } })
}

export const getStoryConsole = (storyId, fromLine = 0) => {
  return service.get(`/api/story/${storyId}/console-log`, { params: { from_line: fromLine } })
}

export const getStorySession = (storyId) => {
  return service.get(`/api/story/${storyId}`)
}

export const selectNextTopic = (storyId, topicId) => {
  return requestWithRetry(
    () => service.post(`/api/story/${storyId}/choose-topic`, { topic_id: topicId }),
    3,
    1000
  )
}

export const restartCurrentChapter = (storyId) => {
  return requestWithRetry(
    () => service.post(`/api/story/${storyId}/restart-current`, {}),
    3,
    1000
  )
}

export const confirmBlueprint = (storyId) => {
  return requestWithRetry(
    () => service.post(`/api/story/${storyId}/confirm-blueprint`, {}),
    3,
    1000
  )
}

export const regenerateBlueprint = (storyId, data = {}) => {
  return requestWithRetry(
    () => service.post(`/api/story/${storyId}/regenerate-blueprint`, data),
    3,
    1000
  )
}

export const getStorySessionBySimulation = (simulationId) => {
  return service.get(`/api/story/by-simulation/${simulationId}`)
}

export const listStorySessions = (limit = 12, simulationId = null) => {
  const params = { limit }
  if (simulationId) params.simulation_id = simulationId
  return service.get('/api/story/list', { params })
}

export const chatWithStoryGuide = (data) => {
  return requestWithRetry(() => service.post('/api/story/chat', data), 3, 1000)
}

// Backward-compatible aliases for views that still use report terminology.
export const generateReport = createStorySession
export const getReportStatus = getStorySessionStatus
export const getAgentLog = getStoryLogs
export const getConsoleLog = getStoryConsole
export const getReport = getStorySession
export const chooseTopic = selectNextTopic
export const getReportBySimulation = getStorySessionBySimulation
export const listReports = listStorySessions
export const chatWithReport = chatWithStoryGuide
