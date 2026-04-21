<template>
  <a-page-header title="大模型配置" subtitle="配置 AI 摘要和 AI 报告生成使用的大模型参数">
    <a-card :bordered="false">
      <a-spin :loading="loading" tip="加载中...">
        <a-form :model="config" layout="vertical" style="max-width: 600px;">
          <a-form-item label="API 地址" required help="大模型 API 的访问地址，支持 OpenAI 兼容接口">
            <a-input v-model="config.api_url" placeholder="例如: https://api.openai.com/v1" allow-clear />
          </a-form-item>

          <a-form-item label="API Key" required help="用于认证的密钥，请妥善保管">
            <a-input-password v-model="config.api_key" placeholder="请输入 API Key" allow-clear />
          </a-form-item>

          <a-form-item label="模型名称" help="要使用的模型名称，如 gpt-3.5-turbo、gpt-4 等">
            <a-input v-model="config.model" placeholder="gpt-3.5-turbo" allow-clear />
          </a-form-item>

          <a-form-item>
            <a-space>
              <a-button type="primary" :loading="saving" @click="handleSave">
                <template #icon><icon-save /></template>
                保存配置
              </a-button>
              <a-button @click="handleTest" :loading="testing">
                <template #icon><icon-thunderbolt /></template>
                测试连接
              </a-button>
            </a-space>
          </a-form-item>
        </a-form>
      </a-spin>

      <a-divider />

      <a-alert type="info" style="margin-top: 12px;">
        <template #title>使用说明</template>
        <ul style="margin: 4px 0 0 0; padding-left: 16px; line-height: 2;">
          <li>此处配置的大模型参数将用于「AI 摘要」和「AI 报告生成」功能</li>
          <li>支持所有兼容 OpenAI Chat Completions API 的服务</li>
          <li>API Key 将加密存储在数据库中，请确保使用 HTTPS 连接</li>
        </ul>
      </a-alert>
    </a-card>
  </a-page-header>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconSave, IconThunderbolt } from '@arco-design/web-vue/es/icon'
import { getLLMConfig, saveLLMConfig } from '@/api/llmConfig'

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

const config = ref({
  api_url: '',
  api_key: '',
  model: 'gpt-3.5-turbo'
})

const fetchConfig = async () => {
  loading.value = true
  try {
    const res = await getLLMConfig()
    config.value.api_url = res.api_url || ''
    config.value.api_key = res.api_key || ''
    config.value.model = res.model || 'gpt-3.5-turbo'
  } catch (error) {
    // 首次使用可能没有配置，不报错
    console.log('加载大模型配置:', error)
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  if (!config.value.api_url) {
    Message.warning('请输入 API 地址')
    return
  }
  if (!config.value.api_key) {
    Message.warning('请输入 API Key')
    return
  }

  saving.value = true
  try {
    await saveLLMConfig(config.value)
    Message.success('大模型配置已保存')
  } catch (error) {
    Message.error(String(error || '保存失败'))
  } finally {
    saving.value = false
  }
}

const handleTest = async () => {
  if (!config.value.api_url || !config.value.api_key) {
    Message.warning('请先填写 API 地址和 API Key')
    return
  }

  testing.value = true
  try {
    const url = config.value.api_url.replace(/\/$/, '')
    const endpoint = url.endsWith('/chat/completions') ? url : `${url}/chat/completions`
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${config.value.api_key}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: config.value.model || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: 'Hi' }],
        max_tokens: 5
      })
    })

    if (response.ok) {
      Message.success('连接测试成功！大模型可正常访问')
    } else {
      const text = await response.text()
      Message.error(`连接失败 (${response.status}): ${text.substring(0, 200)}`)
    }
  } catch (error: any) {
    Message.error(`连接失败: ${error.message || '无法访问 API 地址'}`)
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  fetchConfig()
})
</script>
