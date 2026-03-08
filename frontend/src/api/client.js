import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: attach Bearer token
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: redirect to /login on 401
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authAPI = {
  getMe: () => client.get('/auth/me'),
  logout: () => client.post('/auth/logout'),
}

// ── Projects ──────────────────────────────────────────────────────────────────

export const projectsAPI = {
  list: () => client.get('/projects'),
  get: (id) => client.get(`/projects/${id}`),
  create: (data) => client.post('/projects', data),
  update: (id, data) => client.put(`/projects/${id}`, data),
  delete: (id) => client.delete(`/projects/${id}`),
  // webhook_secret doubles as the runner registration token
  getRunnerToken: (id) => client.get(`/projects/${id}`),
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

export const jobsAPI = {
  listAll: (params) => client.get('/jobs', { params }),
  listByProject: (projectId, params) =>
    client.get('/jobs', { params: { ...params, project_id: projectId } }),
  get: (id) => client.get(`/jobs/${id}`),
  approve: (id) => client.post(`/jobs/${id}/approve`),
  reject: (id, reason) => client.post(`/jobs/${id}/reject`, { reason }),
}

export default client
