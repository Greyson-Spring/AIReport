<template>
  <a-modal v-model:visible="visible" title="AI 文章摘要" :width="720" :footer="false" @cancel="handleCancel">
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

    <!-- 提示词 -->
    <a-form-item label="自定义提示词" style="margin-bottom: 12px;">
      <a-textarea
        v-model="prompt"
        :max-length="2000"
        :auto-size="{ minRows: 2, maxRows: 6 }"
        placeholder="请对以下文章内容进行摘要总结，提取关键信息，以简洁清晰的方式呈现要点..."
        show-word-limit
        allow-clear
      />
    </a-form-item>

    <!-- 已选文章 -->
    <div style="margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
      <span style="color: var(--color-text-3); font-size: 13px;">
        已选择 <a-tag color="blue">{{ articleIds.length }}</a-tag> 篇文章
      </span>
      <a-checkbox v-model="saveToDb">
        <span style="font-size: 13px;">保存摘要到文章</span>
      </a-checkbox>
    </div>
    <div v-if="saveToDb" style="margin-bottom: 12px;">
      <a-alert type="info">开启后将逐篇生成摘要并写入数据库 description 字段，多篇文章耗时较长</a-alert>
    </div>

    <!-- 操作按钮 -->
    <a-button type="primary" :loading="loading" @click="handleSubmit" long>
      <template #icon><icon-robot /></template>
      生成摘要
    </a-button>

    <!-- 结果区域 -->
    <div v-if="result" style="margin-top: 16px;">
      <a-divider style="margin: 12px 0;" />
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
        <span style="font-weight: 600;">摘要结果</span>
        <a-space size="small">
          <a-tag size="small" color="green">{{ result.model }}</a-tag>
          <a-tag size="small">{{ result.article_count }} 篇文章</a-tag>
          <a-button type="text" size="mini" @click="copyResult">
            <template #icon><icon-copy /></template>
          </a-button>
        </a-space>
      </div>
      <div class="ai-result-content" v-html="renderedResult"></div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconRobot, IconCopy } from '@arco-design/web-vue/es/icon'
import { aiSummary } from '@/api/ai'
import { getLLMConfig } from '@/api/llmConfig'
import { useRouter } from 'vue-router'

const router = useRouter()

const visible = ref(false)
const loading = ref(false)
const articleIds = ref<string[]>([])
const result = ref<{ summary: string; article_count: number; model: string; failed_ids?: string[] } | null>(null)
const saveToDb = ref(true)

const prompt = ref('')

const config = ref({
  api_url: '',
  api_key: '',
  model: 'gpt-3.5-turbo'
})

const configSaved = computed(() => !!config.value.api_url && !!config.value.api_key)

// 简单将换行转为 <br>、段落分隔
const renderedResult = computed(() => {
  if (!result.value?.summary) return ''
  return result.value.summary
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
})

// 从后端加载大模型配置
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
    const savedPrompt = localStorage.getItem('ai_summary_prompt')
    if (savedPrompt) {
      prompt.value = savedPrompt
    }
  } catch {}
}

const goToLLMConfig = () => {
  visible.value = false
  router.push('/llm-config')
}

const show = async (ids: string[]) => {
  articleIds.value = ids
  result.value = null
  visible.value = true
  await loadConfig()
}

const hide = () => {
  visible.value = false
}

const handleCancel = () => {
  hide()
}

const handleSubmit = async () => {
  if (!articleIds.value.length) {
    Message.warning('请先选择文章')
    return
  }
  if (!config.value.api_url) {
    Message.warning('请先前往「大模型配置」页面配置 API 地址')
    return
  }
  if (!config.value.api_key) {
    Message.warning('请先前往「大模型配置」页面配置 API Key')
    return
  }

  loading.value = true
  result.value = null

  try {
    const res = await aiSummary({
      article_ids: articleIds.value,
      prompt: prompt.value || undefined,
      api_url: config.value.api_url,
      api_key: config.value.api_key,
      model: config.value.model || undefined,
      save_to_db: saveToDb.value
    })
    result.value = res
    if (saveToDb.value) {
      Message.success(res.summary || `已为 ${res.article_count} 篇文章生成并保存摘要`)
    }
    // 保存提示词
    if (prompt.value) {
      localStorage.setItem('ai_summary_prompt', prompt.value)
    }
  } catch (error) {
    Message.error(String(error || 'AI摘要生成失败'))
  } finally {
    loading.value = false
  }
}

const copyResult = async () => {
  if (!result.value?.summary) return
  try {
    await navigator.clipboard.writeText(result.value.summary)
    Message.success('已复制到剪贴板')
  } catch {
    Message.error('复制失败')
  }
}

defineExpose({ show, hide })
</script>

<style scoped>
.ai-result-content {
  background: var(--color-fill-1);
  border-radius: 8px;
  padding: 16px;
  line-height: 1.8;
  font-size: 14px;
  color: var(--color-text-1);
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
