import axios from 'axios'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 120000
})

http.interceptors.response.use(
  (res) => res.data.data,
  (err) => {
    const msg = err.response?.data?.error || err.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

export const api = {
  create: (seed, files = [], style = '', styleNotes = '') => {
    const form = new FormData()
    form.append('seed', seed)
    form.append('style', style)
    form.append('style_notes', styleNotes)
    files.forEach((f) => form.append('files', f))
    return http.post('/api/story', form)
  },
  styles: () => http.get('/api/story/styles'),
  setStyle: (id, style, styleNotes) => http.post(`/api/story/${id}/style`, { style, style_notes: styleNotes }),
  list: () => http.get('/api/story/list'),
  get: (id) => http.get(`/api/story/${id}`),
  remove: (id) => http.delete(`/api/story/${id}`),
  timeline: (id) => http.get(`/api/story/${id}/timeline`),
  regenerateBlueprint: (id, instruction) => http.post(`/api/story/${id}/blueprint/regenerate`, { instruction }),
  confirmBlueprint: (id) => http.post(`/api/story/${id}/blueprint/confirm`),
  choose: (id, payload) => http.post(`/api/story/${id}/choose`, payload),
  regenerateChapter: (id) => http.post(`/api/story/${id}/regenerate-chapter`),
  rewind: (id, keep) => http.post(`/api/story/${id}/rewind`, { keep_chapters: keep }),
  retry: (id) => http.post(`/api/story/${id}/retry`),
  downloadUrl: (id) => `${import.meta.env.VITE_API_BASE_URL || ''}/api/story/${id}/download`
}
