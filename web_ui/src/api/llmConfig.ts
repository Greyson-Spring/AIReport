import http from './http'

export interface LLMConfig {
  api_url: string
  api_key: string
  model: string
}

export const getLLMConfig = (): Promise<LLMConfig> => {
  return http.get('/wx/llm-config')
}

export const saveLLMConfig = (data: LLMConfig): Promise<any> => {
  return http.put('/wx/llm-config', data)
}
