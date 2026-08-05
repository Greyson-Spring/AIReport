import http from './http'

export interface AISummaryParams {
  article_ids: string[]
  prompt?: string
  api_url?: string
  api_key?: string
  model?: string
  save_to_db?: boolean
}

export interface AISummaryResult {
  summary: string
  article_count: number
  model: string
  failed_ids?: string[]
}

export const aiSummary = (params: AISummaryParams): Promise<AISummaryResult> => {
  return http.post('/wx/ai/summary', params, { timeout: 2000000 })
}

export interface AIReportParams {
  start_date: string
  end_date: string
  prompt?: string
  api_url?: string
  api_key?: string
  model?: string
  mp_id?: string
  keyword?: string
  source?: string      // 新增：all, favorite, folder, mp
  folder_id?: number   // 新增：文件夹ID
}

export interface AIReportPreviewResult {
  report: string
  article_count: number
  date_range: string
  model: string
  history_id?: number  // l历史记录ID
}

export const aiReportPreview = (params: AIReportParams): Promise<AIReportPreviewResult> => {
  return http.post('/wx/ai/report/preview', params, { timeout: 2000000 })
}

export const aiReportDownload = (params: AIReportParams): Promise<Blob> => {
  return http.post('/wx/ai/report', params, {
    timeout: 2000000,
    responseType: 'blob'
  })
}

// ===== AI 问答 =====

export interface AIQAParams {
  question: string
  api_url?: string
  api_key?: string
  model?: string
  mp_id?: string
}

export interface AIQASource {
  index: number
  title: string
  mp_name: string
  url: string
  publish_date: string
}

export interface AIQAResult {
  answer: string
  sources: AIQASource[]
  article_count: number
  model: string
}

export const aiQA = (params: AIQAParams): Promise<AIQAResult> => {
  return http.post('/wx/ai/qa', params, { timeout: 120000 })
}
/**
 * 导出历史报告（直接返回 Word 文件）
 * @param historyId 历史记录ID
 * @returns Blob 文件流
 */
export const exportHistoryReport = (historyId: number): Promise<Blob> => {
  return http.get(`/wx/ai/history/export/${historyId}`, {
    responseType: 'blob'
  })
}
/**
 * 删除历史报告
 * @param historyId 历史记录ID
 */
export const deleteHistoryReport = (historyId: number): Promise<any> => {
  return http.delete(`/wx/ai/history/${historyId}`)
}
