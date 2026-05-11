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
        <div class="section-label">模型配置</div>
        <a-tag color="green" size="small">{{ config.model || 'gpt-3.5-turbo' }}</a-tag>
      </div>

      <!-- 数据来源显示（新增） -->
      <div class="panel-section">
        <div class="section-label">数据来源</div>
        <a-tag color="blue">{{ sourceLabel }}</a-tag>
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
      <!-- 历史记录区域 -->
      <div class="panel-section history-panel-section">
        <div class="section-label" style="display: flex; justify-content: space-between; align-items: center;">
          <span>📋 历史报告</span>
          <a-button size="mini" type="text" @click="fetchHistoryList" :loading="historyLoading">
            <template #icon><icon-refresh /></template>
          </a-button>
        </div>
        
        <div v-if="historyLoading" class="history-loading">
          <a-spin size="small" /> 加载中...
        </div>
        
        <div v-else-if="historyList.length === 0" class="history-empty">
          暂无历史报告
        </div>
        
        <div v-else class="history-list">
          <div 
            v-for="item in historyList" 
            :key="item.id"
            class="history-item"
            :class="{ 'history-item-active': activeHistoryId === item.id }"
          >
            <!-- 可点击的内容区域（加载报告） -->
            <div class="history-item-content" @click="loadHistoryReport(item)">
              <div class="history-item-title">{{ item.title }}</div>
              <div class="history-item-time">{{ item.created_at }}</div>
            </div>
            <!-- 删除按钮（默认隐藏，hover 时显示） -->
            <a-button 
              class="history-item-delete"
              size="mini" 
              type="text" 
              status="danger"
              @click.stop="confirmDeleteHistory(item)"
            >
              <template #icon><icon-delete /></template>
            </a-button>
          </div>

        </div>
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
import { deleteHistoryReport } from '@/api/ai'
import { Modal } from '@arco-design/web-vue'

const route = useRoute()
const router = useRouter()
// 数据来源相关变量
const source = ref('all')        // all, favorite, folder
const folderId = ref('')         // 文件夹ID
const folderName = ref('')       // 文件夹名称

const editorRef = ref<HTMLDivElement | null>(null)
const previewLoading = ref(false)
const downloadLoading = ref(false)
const mpId = ref('')
const mpName = ref('')
const keyword = ref('')
const currentFontSize = ref('3')
const currentHeading = ref('p')
const reportMeta = ref<{ model: string; article_count: number; date_range: string } | null>(null)
// 历史记录相关 
const historyList = ref([])           // 历史记录列表
const historyLoading = ref(false)     // 加载中状态
const activeHistoryId = ref(null)     // 当前选中的历史记录ID
const isViewingHistory = ref(false)   // 是否正在查看历史记录
const currentHistoryId = ref(null)    // 当前查看的历史记录ID

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
// 数据来源显示文本
const sourceLabel = computed(() => {
  if (source.value === 'favorite') return '精选文章'
  if (source.value === 'folder') return folderName.value
  // 单个公众号：显示公众号名称
  if (mpId.value) return `公众号：${mpName.value}`
  // 默认显示全站
  return '全部文章'
})
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
  
  const params: any = {
    start_date: dateRange.value[0],
    end_date: dateRange.value[1],
    prompt: prompt.value || undefined,
    api_url: config.value.api_url,
    api_key: config.value.api_key,
    model: config.value.model || undefined,
    keyword: keyword.value || undefined,
    source: source.value  // 新增：传递数据来源
  }
  
  // 根据来源类型传递不同参数
  if (source.value === 'folder') {
    // 文件夹：传 folder_id
    params.folder_id = folderId.value
    params.folder_name = folderName.value
  } else {
    // 全部或精选文章：传 mp_id（精选文章时 mp_id 可为空，表示全站）
    params.mp_id = mpId.value || undefined
  }
  
  return params
}

// ---- 生成报告 ----
const handlePreview = async () => {
  const params = getRequestParams()
  if (!params) return

  previewLoading.value = true
  reportMeta.value = null
  
  try {
    const res = await aiReportPreview(params)
    // 保存新生成的报告 ID，用于后续导出
    if (res.history_id) {
      currentHistoryId.value = res.history_id
      isViewingHistory.value = true  // 标记为"正在查看刚生成的报告"
    }
    // 保存报告元信息
    reportMeta.value = {
      model: res.model,
      article_count: res.article_count,
      date_range: res.date_range
    }
    
    // 直接使用 res.report（已经是完整的 Markdown）
    const fullMarkdown = res.report
    
    // 保存提示词到本地存储
    if (prompt.value) {
      localStorage.setItem('ai_report_prompt', prompt.value)
    }
    
    // 关闭 loading，重新渲染编辑器
    previewLoading.value = false
    await nextTick()
    
    // 显示到编辑器
    if (editorRef.value) {
      const htmlContent = markdownToHtml(fullMarkdown)
      editorRef.value.innerHTML = htmlContent
      hasContent.value = true
    }
    
    // ========== ⭐刷新历史记录列表 ==========
    // 生成新报告后，后端已经自动保存，需要刷新左侧列表
    await fetchHistoryList()
    
    // 可选：自动选中最新生成的记录（第一条）
    if (historyList.value.length > 0) {
      activeHistoryId.value = historyList.value[0]?.id
    }
    
    Message.success('报告生成成功，已自动保存到历史记录')
    
  } catch (error) {
    Message.error(String(error || 'AI报告生成失败'))
    previewLoading.value = false
  }
}

// ---- 导出 Word ----
/* const handleDownload = async () => {
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
} */
const handleDownload = async () => {
  // 如果正在查看历史记录，直接导出保存的报告
  if (isViewingHistory.value && currentHistoryId.value) {
    await exportSavedReport()
    return
  }
  
  // 否则，走原来的逻辑：重新调用 AI 生成
  await generateAndDownload()
}

// 导出保存的历史报告
const exportSavedReport = async () => {
  downloadLoading.value = true
  try {
    // 动态导入 exportHistoryReport 函数
    const { exportHistoryReport } = await import('@/api/ai')
    
    const blob = await exportHistoryReport(currentHistoryId.value)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    // 从响应头获取文件名，或使用默认名称
    const contentDisposition = blob.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      ? 'document.docx'
      : `history_report_${currentHistoryId.value}.docx`
    a.download = contentDisposition
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    Message.success('历史报告导出成功')
  } catch (error) {
    console.error('导出历史报告失败:', error)
    Message.error(String(error || '导出失败'))
  } finally {
    downloadLoading.value = false
  }
}

// 重新生成并下载（原有逻辑）
const generateAndDownload = async () => {
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
// ========== 获取历史记录列表 ==========
// 获取历史记录列表
const fetchHistoryList = async () => {
  historyLoading.value = true
  try {
    const token = localStorage.getItem('token')
    const response = await fetch('/api/v1/wx/ai/history/list', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const result = await response.json()
    if (result.code === 0 && result.data) {
      historyList.value = result.data.list || []
      console.log('历史记录加载成功:', historyList.value.length, '条')
    } else {
      console.error('获取历史记录失败:', result)
    }
  } catch (error) {
    console.error('获取历史记录出错:', error)
  } finally {
    historyLoading.value = false
  }
}
// 加载历史报告
const loadHistoryReport = async (item) => {
  console.log('folderName 变量:', folderName)  // ⭐ 添加这行
  console.log('folderName.value:', folderName.value)
  console.log('加载历史报告:', item.title)
  
  // 设置历史查看状态
  isViewingHistory.value = true
  currentHistoryId.value = item.id
  activeHistoryId.value = item.id
  
  // 1. 回填左侧配置（方便用户基于此修改后重新生成）
  dateRange.value = [item.start_date, item.end_date]
  keyword.value = item.keyword || ''
  prompt.value = item.prompt || ''
  
  // 2. 根据来源类型设置显示
  if (item.source === 'mp') {
    mpId.value = item.mp_id || ''
    mpName.value = item.mp_name || item.mp_id || ''
    source.value = 'mp'
  } else if (item.source === 'folder') {
    folderId.value = String(item.folder_id || '')
    folderName.value = item.folder_name || '文件夹'
    source.value = 'folder'
  } else if (item.source === 'favorite') {
    source.value = 'favorite'
    mpId.value = ''
    mpName.value = '精选文章'
  } else {
    source.value = 'all'
    mpId.value = ''
    mpName.value = '全部'
  }
  
  // 3. 将报告内容显示到编辑器
 // 简化：直接使用 item.report_content（已经是完整的 Markdown）⭐⭐⭐
  if (editorRef.value) {
    const htmlContent = markdownToHtml(item.report_content)
    editorRef.value.innerHTML = htmlContent
    hasContent.value = true
  }
  
  Message.success(`已加载报告：${item.title}`)
}
/**
 * 确认删除历史记录
 * 原理：
 * 1. 弹出确认对话框
 * 2. 用户确认后调用删除 API
 * 3. 删除成功后刷新列表
 * 4. 如果删除的是当前正在查看的记录，清空编辑器
 */
const confirmDeleteHistory = (item) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除报告「${item.title}」吗？删除后无法恢复。`,
    okText: '确认删除',
    cancelText: '取消',
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      try {
        // 调用删除 API
        await deleteHistoryReport(item.id)
        Message.success('删除成功')
        
        // 刷新历史记录列表
        await fetchHistoryList()
        
        // 如果删除的是当前正在查看的记录，清空编辑器内容
        if (activeHistoryId.value === item.id) {
          activeHistoryId.value = null
          isViewingHistory.value = false
          currentHistoryId.value = null
          if (editorRef.value) {
            editorRef.value.innerHTML = `
              <h1 style="text-align:center; color: #333;">公众号文章分析报告</h1>
              <p style="text-align:center; color: #999;">点击左侧「生成报告」，AI 将根据筛选条件自动撰写报告内容</p>
              <p style="text-align:center; color: #999;">生成后您可以直接在此编辑文字、调整格式</p>
            `
            hasContent.value = false
          }
        }
      } catch (error) {
        console.error('删除失败:', error)
        Message.error(String(error || '删除失败'))
      }
    }
  })
}
// ---- 初始化 ----
onMounted(async () => {
  mpId.value = (route.query.mpId as string) || ''
  mpName.value = (route.query.mpName as string) || '全部'
  // 获取数据来源参数
  source.value = (route.query.source as string) || 'all'
  
  if (source.value === 'folder') {
    folderId.value = (route.query.folder_id as string) || ''
    folderName.value = (route.query.folder_name as string) || (route.query.mpName as string) || '文件夹'
  }
  // 如果没有传 mpName 但有 mpId，尝试从 mpId 生成一个默认名称
  if (mpId.value && !mpName.value) {
    mpName.value = `公众号(${mpId.value.substring(0, 8)})`
  }
  await loadConfig()
  // 加载历史记录列表
  await fetchHistoryList()
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
/* 历史记录区域 */
.history-panel-section {
  border-top: 1px solid var(--color-neutral-3);
  margin-top: 8px;
  padding-top: 12px;
  flex-shrink: 0;
}

.history-list {
  max-height: 300px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
/* 历史记录项：左右布局 */
.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: var(--color-fill-1);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
}
/* 悬浮效果 */
.history-item:hover {
  background: var(--color-primary-light-1);
  /* border-color: var(--color-primary-3); */
}
/* 当前选中的记录 */
.history-item-active {
  background: var(--color-primary-light-1);
  /* border-color: var(--color-primary-4); */
}
/* 可点击的内容区域（占满剩余空间） */
.history-item-content {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

/* 删除按钮：默认透明，hover 时显示 */
.history-item-delete {
  opacity: 0;
  transition: all 0.2s ease;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50% !important;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
/* 删除按钮 hover 时的样式 */
.history-item-delete:hover {
  background-color: rgba(255, 77, 79, 0.1) !important;
  color: #ff4d4f !important;
}
/* 删除按钮 hover 时图标也变红 */
.history-item-delete:hover .arco-icon {
  color: #ff4d4f;
}
/* 悬浮在整条记录上时，删除按钮显示 */
.history-item:hover .history-item-delete {
  opacity: 1;
}

/* 标题样式 */
.history-item-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-1);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 时间样式 */
.history-item-time {
  font-size: 10px;
  color: var(--color-text-3);
}

/* 空状态样式 */
.history-empty, .history-loading {
  text-align: center;
  padding: 16px;
  color: var(--color-text-3);
  font-size: 12px;
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
