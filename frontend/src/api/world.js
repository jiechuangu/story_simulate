import service, { requestWithRetry } from './index'

export const bootstrapWorld = (data) => {
  return requestWithRetry(() => service.post('/api/world/bootstrap', data), 2, 1000)
}

export const getWorldState = (simulationId) => {
  return service.get(`/api/world/${simulationId}`)
}

export const claimWorldCharacter = (simulationId, data) => {
  return service.post(`/api/world/${simulationId}/claim`, data)
}

export const createWorldCharacter = (simulationId, data) => {
  return service.post(`/api/world/${simulationId}/characters`, data)
}

export const releaseWorldCharacter = (simulationId) => {
  return service.post(`/api/world/${simulationId}/release`)
}

export const advanceWorldTime = (simulationId, data) => {
  return service.post(`/api/world/${simulationId}/advance-time`, data)
}

export const addWorldFact = (simulationId, data) => {
  return service.post(`/api/world/${simulationId}/facts`, data)
}

export const listWorldImageTasks = (simulationId) => {
  return service.get(`/api/world/${simulationId}/image-tasks`)
}

export const createWorldImageTask = (simulationId, data) => {
  return requestWithRetry(() => service.post(`/api/world/${simulationId}/image-tasks`, data), 1, 1000)
}

export const processWorldDialogue = (simulationId, data) => {
  return service.post(`/api/world/${simulationId}/dialogue`, data)
}

export const fetchDirectorNode = (simulationId, data) => {
  return service.post(`/api/world/${simulationId}/director/node`, data)
}

export const fetchWorldIntroPlan = (simulationId, data) => {
  return service.post(`/api/world/${simulationId}/intro-plan`, data)
}
