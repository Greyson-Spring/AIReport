<template>
  <a-modal v-model:visible="visible" title="AI 报告生成" :width="780" :footer="false" @cancel="handleCancel">
    <!-- 配置状态提示 -->
    <div v-if="!configSaved" style="margin-bottom: 12px;">
      <a-alert type="warning">
        大模型未配置，请先前往
        <a-link @click="goToLLMConfig">大模型配置</a-link>
        页面完成设置
      </a-alert>
    </div>
    <div v-else style="margin-bottom: 12px;">
      <a-alert type="success" :closable="true">
        当前模型：{{ config.model || 'gpt-3.5-turbo' }} | API：{{ config.api_url }}
      </a-alert>
    </div>

    <!-- 筛选条件 -->
    <a-form layout="vertical" size="small">
      <a-form-item label="文章日期范围" required>
        <a-range-picker
          v-model="dateRange"
          style="width: 100%;"
          :allow-clear="true"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
        />
      </a-form-item>

      <a-form-item label="关键字搜索">
        <a-input
          v-model="keyword"
          placeholder="搜索文章标题或摘要内容"
          allow-clear
        />
      </a-form-item>

      <!-- 自定义提示词 -->
      <a-form-item label="自定义提示词">
        <a-textarea
          v-model="prompt"
          :max-length="3000"
          :auto-size="{ minRows: 3, maxRows: 8 }"
          placeholder="你是一个专业的行业分析师。请根据以下多篇文章的摘要信息，生成一份结构化的分析报告..."
          show-word-limit
          allow-clear
        />
      </a-form-item>
    </a-form>

    <!-- 当前公众号信息 -->
    <div style="margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
      <span style="color: var(--color-text-3); font-size: 13px;">
        当前公众号：<a-tag color="blue">{{ mpName || '全部' }}</a-tag>
      </span>
    </div>

    <!-- 操作按钮 -->
    <a-space style="width: 100%;" direction="vertical" :size="8">
      <a-button type="primary" :loading="previewLoading" @click="handlePreview" long>
        <template #icon><icon-eye /></template>
        预览报告
      </a-button>
      <a-button type="primary" status="success" :loading="downloadLoading" @click="handleDownload" long :disabled="!previewResult">
        <template #icon><icon-download /></template>
        导出 Word 文档
      </a-button>
    </a-space>

    <!-- 预览区域 -->
    <div v-if="previewResult" style="margin-top: 16px;">
      <a-divider style="margin: 12px 0;" />
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
        <span style="font-weight: 600;">报告预览</span>
        <a-space size="small">
          <a-tag size="small" color="green">{{ previewResult.model }}</a-tag>
          <a-tag size="small">{{ previewResult.article_count }} 篇文章</a-tag>
          <a-tag size="small" color="arcoblue">{{ previewResult.date_range }}</a-tag>
          <a-button type="text" size="mini" @click="copyResult">
            <template #icon><icon-copy /></template>
          </a-button>
        </a-space>
      </div>
      <div class="ai-report-content" v-html="renderedReport"></div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconEye, IconDownload, IconCopy } from '@arco-design/web-vue/es/icon'
import { aiReportPreview, aiReportDownload } from '@/api/ai'
import { getLLMConfig } from '@/api/llmConfig'
import { useRouter } from 'vue-router'

const router = useRouter()

const visible = ref(false)
const previewLoading = ref(false)
const downloadLoading = ref(false)
const mpId = ref('')
const mpName = ref('')
const keyword = ref('')

const getDefaultDateRange = (): string[] => {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth()
  const firstDay = `${year}-${String(month + 1).padStart(2, '0')}-01`
  const lastDay = new Date(year, month + 1, 0).getDate()
  const lastDayStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`
  return [firstDay, lastDayStr]
}

const dateRange = ref<string[]>(getDefaultDateRange())
const prompt = ref('')
const previewResult = ref<{ report: string; article_count: number; date_range: string; model: string } | null>(null)

const config = ref({
  api_url: '',
  api_key: '',
  model: 'gpt-3.5-turbo'
})

const configSaved = computed(() => !!config.value.api_url && !!config.value.api_key)

const renderedReport = computed(() => {
  if (!previewResult.value?.report) return ''
  return previewResult.value.report
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
})

const loadConfig = async () => {
  try {
    const res = await getLLMConfig()
    config.value.api_url = res.api_url || ''
    config.value.api_key = res.api_key || ''
    config.value.model = res.model || 'gpt-3.5-turbo'
  } catch {
    // 未配置时不报错
  }
  try {
    const savedPrompt = localStorage.getItem('ai_report_prompt')
    if (savedPrompt) {
      prompt.value = savedPrompt
    }
  } catch {}
}

const goToLLMConfig = () => {
  visible.value = false
  router.push('/llm-config')
}

const show = async (currentMpId?: string, currentMpName?: string) => {
  mpId.value = currentMpId || ''
  mpName.value = currentMpName || '全部'
  dateRange.value = getDefaultDateRange()
  keyword.value = ''
  previewResult.value = null
  visible.value = true
  await loadConfig()
}

const handleCancel = () => {
  visible.value = false
}

const getRequestParams = () => {
  if (!dateRange.value || dateRange.value.length !== 2) {
    Message.warning('请选择文章日期范围')
    return null
  }
  if (!config.value.api_url) {
    Message.warning('请先前往「大模型配置」页面配置 API 地址')
    return null
  }
  if (!config.value.api_key) {
    Message.warning('请先前往「大模型配置」页面配置 API Key')
    return null
  }
  return {
    start_date: dateRange.value[0],
    end_date: dateRange.value[1],
    prompt: prompt.value || undefined,
    api_url: config.value.api_url,
    api_key: config.value.api_key,
    model: config.value.model || undefined,
    mp_id: mpId.value || undefined,
    keyword: keyword.value || undefined
  }
}

const handlePreview = async () => {
  const params = getRequestParams()
  if (!params) return

  previewLoading.value = true
  previewResult.value = null
  try {
    const res = await aiReportPreview(params)
    previewResult.value = res
    if (prompt.value) {
      localStorage.setItem('ai_report_prompt', prompt.value)
    }
  } catch (error) {
    Message.error(String(error || 'AI报告生成失败'))
  } finally {
    previewLoading.value = false
  }
}

const handleDownload = async () => {
  const params = getRequestParams()
  if (!params) return

  downloadLoading.value = true
  try {
    const blob = await aiReportDownload(params)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `AI_Report_${params.start_date}_${params.end_date}.docx`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    Message.success('Word 文档已下载')
  } catch (error) {
    Message.error(String(error || '导出Word失败'))
  } finally {
    downloadLoading.value = false
  }
}

const copyResult = async () => {
  if (!previewResult.value?.report) return
  try {
    await navigator.clipboard.writeText(previewResult.value.report)
    Message.success('已复制到剪贴板')
  } catch {
    Message.error('复制失败')
  }
}

defineExpose({ show })
</script>

<style scoped>
.ai-report-content {
  background: var(--color-fill-1);
  border-radius: 8px;
  padding: 16px;
  max-height: 500px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-text-1);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
