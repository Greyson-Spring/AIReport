import http from './http'

export interface AISummaryTask {
  id: string
  name: string
  prompt?: string
  mps_id: string
  cron_exp: string
  status: number
  created_at?: string
  updated_at?: string
}

export interface AISummaryTaskCreate {
  name: string
  prompt?: string
  mps_id: string
  cron_exp: string
  status: number
}

export interface AISummaryTaskUpdate {
  name?: string
  prompt?: string
  mps_id?: string
  cron_exp?: string
  status?: number
}

export const listAISummaryTasks = (params?: { offset?: number; limit?: number }) => {
  return http.get('/wx/ai-summary-tasks', { params })
}

export const getAISummaryTask = (id: string) => {
  return http.get(`/wx/ai-summary-tasks/${id}`)
}

export const createAISummaryTask = (data: AISummaryTaskCreate) => {
  return http.post('/wx/ai-summary-tasks', data)
}

export const updateAISummaryTask = (id: string, data: AISummaryTaskUpdate) => {
  return http.put(`/wx/ai-summary-tasks/${id}`, data)
}

export const deleteAISummaryTask = (id: string) => {
  return http.delete(`/wx/ai-summary-tasks/${id}`)
}

export const freshAISummaryJobs = () => {
  return http.put('/wx/ai-summary-tasks/job/fresh')
}

export const runAISummaryTask = (id: string) => {
  return http.get(`/wx/ai-summary-tasks/${id}/run`)
}
