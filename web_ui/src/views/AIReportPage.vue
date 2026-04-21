<template>
  <div class="ai-report-page">
    <!-- 左侧控制面板 -->
    <div class="left-panel">
      <div class="panel-header">
        <h3 style="margin: 0;">AI 报告生成</h3>
        <a-button size="small" @click="router.go(-1)">
          <template #icon><icon-left /></template>
          返回
        </a-button>
      </div>

      <!-- 配置状态 -->
      <div v-if="!configSaved" class="panel-section">
        <a-alert type="warning" :show-icon="false">
          大模型未配置，请先前往
          <a-link @click="router.push('/llm-config')">大模型配置</a-link>
          页面设置
        </a-alert>
      </div>
      <div v-else class="panel-section">
        <a-tag color="green" size="small">{{ config.model || 'gpt-3.5-turbo' }}</a-tag>
      </div>

      <!-- 当前公众号 -->
      <div class="panel-section">
        <div class="section-label">当前公众号</div>
        <a-tag color="blue">{{ mpName || '全部' }}</a-tag>
      </div>

      <!-- 日期范围 -->
      <div class="panel-section">
        <div class="section-label">文章日期范围</div>
        <a-range-picker
          v-model="dateRange"
          style="width: 100%;"
          :allow-clear="true"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          size="small"
        />
      </div>

      <!-- 关键字搜索 -->
      <div class="panel-section">
        <div class="section-label">关键字搜索</div>
        <a-input
          v-model="keyword"
          placeholder="搜索标题或摘要"
          allow-clear
          size="small"
        />
      </div>

      <!-- 自定义提示词 -->
      <div class="panel-section">
        <div class="section-label">自定义提示词</div>
        <a-textarea
          v-model="prompt"
          :max-length="3000"
          :auto-size="{ minRows: 8, maxRows: 15 }"
          placeholder="请根据以下文章摘要生成分析报告..."
          show-word-limit
          allow-clear
          size="small"
        />
      </div>

      <!-- 操作按钮 -->
      <div class="panel-section">
        <a-space direction="vertical" style="width: 100%;" :size="8">
          <a-button type="primary" :loading="previewLoading" @click="handlePreview" long>
            <template #icon><icon-eye /></template>
            生成报告
          </a-button>
          <a-button type="primary" status="success" :loading="downloadLoading" @click="handleDownload" long :disabled="!hasContent">
            <template #icon><icon-download /></template>
            导出 Word
          </a-button>
          <a-button @click="copyContent" long :disabled="!hasContent">
            <template #icon><icon-copy /></template>
            复制内容
          </a-button>
        </a-space>
      </div>

      <!-- 报告信息 -->
      <div v-if="reportMeta" class="panel-section">
        <a-space wrap size="mini">
          <a-tag size="small" color="green">{{ reportMeta.model }}</a-tag>
          <a-tag size="small">{{ reportMeta.article_count }} 篇</a-tag>
          <a-tag size="small" color="arcoblue">{{ reportMeta.date_range }}</a-tag>
        </a-space>
      </div>
    </div>

    <!-- 右侧编辑区域 -->
    <div class="right-panel">
      <!-- 工具栏 -->
      <div class="editor-toolbar">
        <a-space :size="2" wrap>
          <a-tooltip content="撤销">
            <a-button size="mini" type="text" @click="execCmd('undo')"><icon-undo /></a-button>
          </a-tooltip>
          <a-tooltip content="重做">
            <a-button size="mini" type="text" @click="execCmd('redo')"><icon-redo /></a-button>
          </a-tooltip>
          <a-divider direction="vertical" />
          <a-tooltip content="加粗">
            <a-button size="mini" type="text" @click="execCmd('bold')"><b>B</b></a-button>
          </a-tooltip>
          <a-tooltip content="斜体">
            <a-button size="mini" type="text" @click="execCmd('italic')"><i>I</i></a-button>
          </a-tooltip>
          <a-tooltip content="下划线">
            <a-button size="mini" type="text" @click="execCmd('underline')"><u>U</u></a-button>
          </a-tooltip>
          <a-tooltip content="删除线">
            <a-button size="mini" type="text" @click="execCmd('strikeThrough')"><s>S</s></a-button>
          </a-tooltip>
          <a-divider direction="vertical" />
          <a-select v-model="currentFontSize" size="mini" style="width: 80px;" @change="changeFontSize" placeholder="字号">
            <a-option v-for="s in fontSizes" :key="s.value" :value="s.value">{{ s.label }}</a-option>
          </a-select>
          <a-select v-model="currentHeading" size="mini" style="width: 80px;" @change="changeHeading" placeholder="段落">
            <a-option value="p">正文</a-option>
            <a-option value="h1">标题1</a-option>
            <a-option value="h2">标题2</a-option>
            <a-option value="h3">标题3</a-option>
            <a-option value="h4">标题4</a-option>
          </a-select>
          <a-divider direction="vertical" />
          <a-tooltip content="左对齐">
            <a-button size="mini" type="text" @click="execCmd('justifyLeft')"><icon-align-left /></a-button>
          </a-tooltip>
          <a-tooltip content="居中">
            <a-button size="mini" type="text" @click="execCmd('justifyCenter')"><icon-align-center /></a-button>
          </a-tooltip>
          <a-tooltip content="右对齐">
            <a-button size="mini" type="text" @click="execCmd('justifyRight')"><icon-align-right /></a-button>
          </a-tooltip>
          <a-divider direction="vertical" />
          <a-tooltip content="无序列表">
            <a-button size="mini" type="text" @click="execCmd('insertUnorderedList')"><icon-unordered-list /></a-button>
          </a-tooltip>
          <a-tooltip content="有序列表">
            <a-button size="mini" type="text" @click="execCmd('insertOrderedList')"><icon-ordered-list /></a-button>
          </a-tooltip>
          <a-divider direction="vertical" />
          <a-tooltip content="插入分割线">
            <a-button size="mini" type="text" @click="execCmd('insertHorizontalRule')"><icon-minus /></a-button>
          </a-tooltip>
          <a-tooltip content="清除格式">
            <a-button size="mini" type="text" @click="execCmd('removeFormat')"><icon-eraser /></a-button>
          </a-tooltip>
        </a-space>
      </div>

      <!-- 编辑器 / Word 风格区域 -->
      <div class="editor-wrapper">
        <div class="paper-container" v-if="!previewLoading">
          <div
            ref="editorRef"
            class="paper"
            contenteditable="true"
            @input="onEditorInput"
            spellcheck="false"
          ></div>
        </div>
        <div v-else class="loading-area">
          <a-spin :size="32" tip="AI 正在生成报告，请稍候..." />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import {
  IconLeft, IconEye, IconDownload, IconCopy,
  IconUndo, IconRedo, IconAlignLeft, IconAlignCenter, IconAlignRight,
  IconUnorderedList, IconOrderedList, IconMinus, IconEraser
} from '@arco-design/web-vue/es/icon'
import { aiReportPreview, aiReportDownload } from '@/api/ai'
import { getLLMConfig } from '@/api/llmConfig'

const route = useRoute()
const router = useRouter()

const editorRef = ref<HTMLDivElement | null>(null)
const previewLoading = ref(false)
const downloadLoading = ref(false)
const mpId = ref('')
const mpName = ref('')
const keyword = ref('')
const currentFontSize = ref('3')
const currentHeading = ref('p')
const reportMeta = ref<{ model: string; article_count: number; date_range: string } | null>(null)

const fontSizes = [
  { label: '12px', value: '1' },
  { label: '14px', value: '3' },
  { label: '16px', value: '4' },
  { label: '18px', value: '5' },
  { label: '24px', value: '6' },
  { label: '32px', value: '7' },
]

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
const config = ref({ api_url: '', api_key: '', model: 'gpt-3.5-turbo' })
const configSaved = computed(() => !!config.value.api_url && !!config.value.api_key)
const hasContent = ref(false)

// ---- 编辑器命令 ----
const execCmd = (command: string, value?: string) => {
  editorRef.value?.focus()
  document.execCommand(command, false, value)
}

const changeFontSize = (val: string) => {
  execCmd('fontSize', val)
}

const changeHeading = (val: string) => {
  execCmd('formatBlock', val === 'p' ? 'p' : val)
}

const onEditorInput = () => {
  hasContent.value = !!editorRef.value?.innerText?.trim()
}

// ---- Markdown → HTML 转换 ----
const markdownToHtml = (md: string): string => {
  let html = md
    // 转义 HTML
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 标题
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')

  // 粗体 / 斜体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')

  // 分割线
  html = html.replace(/^---$/gm, '<hr/>')

  // 无序列表
  html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)

  // 有序列表
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>')

  // 段落（非标签行）
  const lines = html.split('\n')
  const result: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      result.push('<br/>')
    } else if (/^<(h[1-4]|ul|ol|li|hr|br)/.test(trimmed)) {
      result.push(trimmed)
    } else {
      result.push(`<p>${trimmed}</p>`)
    }
  }

  return result.join('\n')
}

// ---- 加载配置 ----
const loadConfig = async () => {
  try {
    const res = await getLLMConfig()
    config.value.api_url = res.api_url || ''
    config.value.api_key = res.api_key || ''
    config.value.model = res.model || 'gpt-3.5-turbo'
  } catch {}
  try {
    const savedPrompt = localStorage.getItem('ai_report_prompt')
    if (savedPrompt) prompt.value = savedPrompt
  } catch {}
}

// ---- 参数校验 ----
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

// ---- 生成报告 ----
const handlePreview = async () => {
  const params = getRequestParams()
  if (!params) return

  previewLoading.value = true
  reportMeta.value = null
  try {
    const res = await aiReportPreview(params)
    reportMeta.value = {
      model: res.model,
      article_count: res.article_count,
      date_range: res.date_range
    }
    const htmlContent = markdownToHtml(res.report)
    if (prompt.value) {
      localStorage.setItem('ai_report_prompt', prompt.value)
    }
    // 先关闭 loading 让 DOM 重新渲染编辑器，再写入内容
    previewLoading.value = false
    await nextTick()
    if (editorRef.value) {
      editorRef.value.innerHTML = htmlContent
      hasContent.value = true
    }
  } catch (error) {
    Message.error(String(error || 'AI报告生成失败'))
    previewLoading.value = false
  }
}

// ---- 导出 Word ----
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

// ---- 复制 ----
const copyContent = async () => {
  if (!editorRef.value) return
  try {
    const text = editorRef.value.innerText || ''
    await navigator.clipboard.writeText(text)
    Message.success('已复制到剪贴板')
  } catch {
    Message.error('复制失败')
  }
}

// ---- 初始化 ----
onMounted(async () => {
  mpId.value = (route.query.mpId as string) || ''
  mpName.value = (route.query.mpName as string) || '全部'
  await loadConfig()

  // 初始占位内容
  if (editorRef.value) {
    editorRef.value.innerHTML = `
      <h1 style="text-align:center; color: #333;">公众号文章分析报告</h1>
      <p style="text-align:center; color: #999;">点击左侧「生成报告」，AI 将根据筛选条件自动撰写报告内容</p>
      <p style="text-align:center; color: #999;">生成后您可以直接在此编辑文字、调整格式</p>
    `
  }
})
</script>

<style scoped>
.ai-report-page {
  display: flex;
  height: calc(100vh - 60px);
  background: #f0f2f5;
}

.left-panel {
  width: 320px;
  min-width: 320px;
  background: #fff;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 16px;
  gap: 12px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.panel-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-label {
  font-size: 12px;
  color: var(--color-text-3);
  font-weight: 500;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-toolbar {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 6px 16px;
  flex-shrink: 0;
}

.editor-wrapper {
  flex: 1;
  overflow-y: auto;
  display: flex;
  justify-content: center;
  padding: 24px;
  background: #e8e8e8;
}

.paper-container {
  width: 100%;
  max-width: 816px; /* A4 宽度近似 */
  min-height: 1056px;
}

.paper {
  background: #fff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  padding: 60px 72px;
  min-height: 1056px;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  font-size: 14px;
  line-height: 1.8;
  color: #333;
  outline: none;
  word-break: break-word;
}

.paper:focus {
  box-shadow: 0 2px 16px rgba(22, 93, 255, 0.15);
}

.paper :deep(h1) {
  font-size: 24px;
  font-weight: 700;
  margin: 20px 0 12px;
  color: #1d2129;
}

.paper :deep(h2) {
  font-size: 20px;
  font-weight: 600;
  margin: 18px 0 10px;
  color: #1d2129;
  border-bottom: 1px solid #e8e8e8;
  padding-bottom: 6px;
}

.paper :deep(h3) {
  font-size: 17px;
  font-weight: 600;
  margin: 14px 0 8px;
  color: #1d2129;
}

.paper :deep(h4) {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 6px;
  color: #4e5969;
}

.paper :deep(p) {
  margin: 8px 0;
  text-indent: 0;
}

.paper :deep(ul), .paper :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.paper :deep(li) {
  margin: 4px 0;
}

.paper :deep(hr) {
  border: none;
  border-top: 1px solid #e8e8e8;
  margin: 16px 0;
}

.paper :deep(strong) {
  font-weight: 600;
}

.loading-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}
</style>
