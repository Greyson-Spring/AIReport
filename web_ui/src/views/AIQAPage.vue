<template>
  <div class="ai-qa-page">
    <!-- 左侧控制面板 -->
    <div class="left-panel">
      <div class="panel-header">
        <h3 style="margin: 0;">AI 问答</h3>
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
        <div class="section-label">数据范围</div>
        <a-tag color="blue">{{ mpName || '全部公众号' }}</a-tag>
      </div>

      <!-- 使用说明 -->
      <div class="panel-section">
        <div class="section-label">使用说明</div>
        <div style="font-size: 12px; color: var(--color-text-3); line-height: 1.8;">
          <p>基于数据库中的文章信息进行问答</p>
          <p>系统会自动检索相关文章，经AI分析后回答</p>
          <p>回答中会标注文章出处 [序号]</p>
        </div>
      </div>

      <!-- 清空对话 -->
      <div class="panel-section">
        <a-button long @click="clearChat" :disabled="messages.length === 0">
          <template #icon><icon-delete /></template>
          清空对话
        </a-button>
      </div>
    </div>

    <!-- 右侧聊天区域 -->
    <div class="right-panel">
      <!-- 消息列表 -->
      <div class="chat-messages" ref="chatContainerRef">
        <div v-if="messages.length === 0" class="empty-hint">
          <div style="font-size: 48px; margin-bottom: 16px;">💬</div>
          <h3 style="color: var(--color-text-2); margin: 0 0 8px;">基于文章数据库的 AI 问答</h3>
          <p style="color: var(--color-text-3); margin: 0;">试试提问：最近有哪些热门话题？/ 关于XX的文章有哪些观点？</p>
        </div>

        <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-message', msg.role]">
          <div class="message-avatar">
            <a-avatar :size="32" v-if="msg.role === 'user'">
              <icon-user />
            </a-avatar>
            <a-avatar :size="32" style="background: linear-gradient(135deg, #165dff, #722ed1);" v-else>
              AI
            </a-avatar>
          </div>
          <div class="message-content">
            <div class="message-bubble" v-html="msg.role === 'assistant' ? renderMarkdown(msg.content) : msg.content"></div>
            <!-- 来源引用 -->
            <div v-if="msg.sources && msg.sources.length > 0" class="message-sources">
              <div class="sources-title">📎 参考来源</div>
              <div v-for="src in msg.sources" :key="src.index" class="source-item">
                <span class="source-index">[{{ src.index }}]</span>
                <a v-if="src.url" :href="src.url" target="_blank" class="source-link">{{ src.title }}</a>
                <span v-else class="source-text">{{ src.title }}</span>
                <span class="source-meta">{{ src.mp_name }} · {{ src.publish_date }}</span>
              </div>
            </div>
            <!-- 统计信息 -->
            <div v-if="msg.meta" class="message-meta">
              <a-tag size="small" color="green">{{ msg.meta.model }}</a-tag>
              <a-tag size="small">匹配 {{ msg.meta.article_count }} 篇文章</a-tag>
            </div>
          </div>
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="chat-message assistant">
          <div class="message-avatar">
            <a-avatar :size="32" style="background: linear-gradient(135deg, #165dff, #722ed1);">AI</a-avatar>
          </div>
          <div class="message-content">
            <div class="message-bubble loading-bubble">
              <a-spin :size="16" /> <span style="margin-left: 8px;">正在检索文章并分析中...</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-area">
        <div class="chat-input-wrapper">
          <a-textarea
            v-model="inputText"
            :auto-size="{ minRows: 5, maxRows: 10 }"
            placeholder="输入您的问题，按 Enter 发送，Shift+Enter 换行"
            @keydown="handleKeydown"
            :disabled="loading"
            class="chat-input"
          />
          <a-button
            type="primary"
            :loading="loading"
            :disabled="!inputText.trim() || !configSaved"
            @click="sendMessage"
            class="send-btn"
          >
            <template #icon><icon-send /></template>
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { IconLeft, IconDelete, IconUser, IconSend } from '@arco-design/web-vue/es/icon'
import { aiQA, type AIQASource } from '@/api/ai'
import { getLLMConfig } from '@/api/llmConfig'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: AIQASource[]
  meta?: { model: string; article_count: number }
}

const route = useRoute()
const router = useRouter()
const chatContainerRef = ref<HTMLDivElement | null>(null)

const mpId = ref('')
const mpName = ref('')
const inputText = ref('')
const loading = ref(false)
const messages = ref<ChatMessage[]>([])
const config = ref({ api_url: '', api_key: '', model: 'gpt-3.5-turbo' })
const configSaved = computed(() => !!config.value.api_url && !!config.value.api_key)

// ---- Markdown 简易渲染 ----
const renderMarkdown = (md: string): string => {
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/\[(\d+)\]/g, '<sup class="ref-tag">[$1]</sup>')
  html = html.replace(/^---$/gm, '<hr/>')
  html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)

  const lines = html.split('\n')
  const result: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      result.push('<br/>')
    } else if (/^<(h[1-4]|ul|ol|li|hr|br|sup)/.test(trimmed)) {
      result.push(trimmed)
    } else {
      result.push(`<p>${trimmed}</p>`)
    }
  }
  return result.join('\n')
}

// ---- 滚动到底部 ----
const scrollToBottom = async () => {
  await nextTick()
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
  }
}

// ---- 发送消息 ----
const sendMessage = async () => {
  const question = inputText.value.trim()
  if (!question || loading.value) return

  messages.value.push({ role: 'user', content: question })
  inputText.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const res = await aiQA({
      question,
      api_url: config.value.api_url,
      api_key: config.value.api_key,
      model: config.value.model || undefined,
      mp_id: mpId.value || undefined
    })
    messages.value.push({
      role: 'assistant',
      content: res.answer,
      sources: res.sources,
      meta: { model: res.model, article_count: res.article_count }
    })
  } catch (e: any) {
    const errMsg = typeof e === 'string' ? e : (e?.message || e?.detail || JSON.stringify(e))
    messages.value.push({
      role: 'assistant',
      content: `抱歉，回答时出现错误：${errMsg}`
    })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

// ---- 快捷键 ----
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// ---- 清空对话 ----
const clearChat = () => {
  messages.value = []
}

// ---- 加载配置 ----
const loadConfig = async () => {
  try {
    const res = await getLLMConfig()
    config.value.api_url = res.api_url || ''
    config.value.api_key = res.api_key || ''
    config.value.model = res.model || 'gpt-3.5-turbo'
  } catch {}
}

onMounted(async () => {
  mpId.value = (route.query.mpId as string) || ''
  mpName.value = (route.query.mpName as string) || '全部公众号'
  await loadConfig()
})
</script>

<style scoped>
.ai-qa-page {
  position: fixed;
  top: 60px;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  overflow: hidden;
  background: #f0f2f5;
}

.left-panel {
  width: 280px;
  min-width: 280px;
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

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.empty-hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.chat-message {
  display: flex;
  gap: 12px;
  max-width: 85%;
}

.chat-message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.chat-message.assistant {
  align-self: flex-start;
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}

.user .message-bubble {
  background: #165dff;
  color: #fff;
  border-top-right-radius: 4px;
}

.assistant .message-bubble {
  background: #fff;
  color: #333;
  border-top-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.loading-bubble {
  display: flex;
  align-items: center;
  color: var(--color-text-3);
}

.assistant .message-bubble :deep(h1) { font-size: 20px; font-weight: 600; margin: 12px 0 6px; }
.assistant .message-bubble :deep(h2) { font-size: 17px; font-weight: 600; margin: 10px 0 4px; }
.assistant .message-bubble :deep(h3) { font-size: 15px; font-weight: 600; margin: 8px 0 4px; }
.assistant .message-bubble :deep(p) { margin: 4px 0; }
.assistant .message-bubble :deep(ul) { padding-left: 20px; margin: 4px 0; }
.assistant .message-bubble :deep(li) { margin: 2px 0; }
.assistant .message-bubble :deep(hr) { border: none; border-top: 1px solid #eee; margin: 8px 0; }
.assistant .message-bubble :deep(strong) { font-weight: 600; }
.assistant .message-bubble :deep(.ref-tag) { color: #165dff; font-weight: 600; cursor: default; }

.message-sources {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 12px;
}

.sources-title {
  font-weight: 500;
  color: var(--color-text-2);
  margin-bottom: 6px;
}

.source-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  line-height: 2;
  flex-wrap: wrap;
}

.source-index {
  color: #165dff;
  font-weight: 600;
  flex-shrink: 0;
}

.source-link {
  color: #165dff;
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}

.source-text {
  color: var(--color-text-1);
}

.source-meta {
  color: var(--color-text-3);
  font-size: 11px;
}

.message-meta {
  display: flex;
  gap: 6px;
}

.chat-input-area {
  border-top: 1px solid #e8e8e8;
  background: #fff;
  padding: 20px 24px;
}

.chat-input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  width: 100%;
}

.chat-input {
  flex: 1;
}

.chat-input :deep(textarea) {
  background: #fff;
  border: 1.5px solid #b8d4ff;
  border-radius: 8px;
}

.chat-input :deep(textarea:focus) {
  border-color: #165dff;
}

.send-btn {
  height: 40px;
  width: 40px;
  flex-shrink: 0;
}
</style>
