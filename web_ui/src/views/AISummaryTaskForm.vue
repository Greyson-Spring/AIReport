<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getAISummaryTask, createAISummaryTask, updateAISummaryTask } from '@/api/aiSummaryTask'
import cronExpressionPicker from '@/components/CronExpressionPicker.vue'
import MpMultiSelect from '@/components/MpMultiSelect.vue'
import { Message } from '@arco-design/web-vue'

const route = useRoute()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const isEditMode = ref(false)
const taskId = ref<string | null>(null)
const showCronPicker = ref(false)
const showMpSelector = ref(false)

const cronPickerRef = ref<InstanceType<typeof cronExpressionPicker> | null>(null)
const mpSelectorRef = ref<InstanceType<typeof MpMultiSelect> | null>(null)

const formData = ref({
  name: '',
  prompt: '',
  mps_id: [] as any[],
  cron_exp: '0 2 * * *',
  status: 1
})

const fetchTaskDetail = async (id: string) => {
  loading.value = true
  try {
    const res = await getAISummaryTask(id)
    formData.value = {
      name: res.name || '',
      prompt: res.prompt || '',
      mps_id: res.mps_id ? JSON.parse(res.mps_id) : [],
      cron_exp: res.cron_exp || '0 2 * * *',
      status: res.status ?? 1
    }
    nextTick(() => {
      if (cronPickerRef.value) {
        cronPickerRef.value.parseExpression(formData.value.cron_exp)
      }
      if (mpSelectorRef.value) {
        mpSelectorRef.value.parseSelected(formData.value.mps_id)
      }
    })
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  try {
    await formRef.value.validate()
  } catch (error: any) {
    Message.error(error?.errors?.join('\n') || '表单验证失败，请检查输入内容')
    return
  }

  loading.value = true
  try {
    const submitData = {
      ...formData.value,
      mps_id: JSON.stringify(formData.value.mps_id)
    }

    if (isEditMode.value && taskId.value) {
      await updateAISummaryTask(taskId.value, submitData)
      Message.success('更新AI摘要任务成功，点击应用按钮后定时任务才会生效')
    } else {
      await createAISummaryTask(submitData)
      Message.success('创建AI摘要任务成功，点击应用按钮后定时任务才会生效')
    }
    setTimeout(() => {
      router.push('/message-tasks')
    }, 1500)
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
  }
}

const rules = {
  name: [
    { required: true, message: '请输入任务名称' },
    { min: 2, max: 50, message: '任务名称长度应在2-50个字符之间' }
  ],
  cron_exp: [
    { required: true, message: '请设置cron表达式' }
  ]
}

onMounted(() => {
  if (route.params.id) {
    isEditMode.value = true
    taskId.value = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id
    if (taskId.value) {
      fetchTaskDetail(taskId.value)
    }
  }
})
</script>

<template>
  <a-spin :loading="loading">
    <div class="ai-summary-task-form">
      <h2>{{ isEditMode ? '编辑AI摘要任务' : '添加AI摘要任务' }}</h2>

      <a-form :model="formData" @submit="handleSubmit" ref="formRef" :rules="rules">
        <a-form-item label="任务名称" field="name" required>
          <a-input
            v-model="formData.name"
            placeholder="请输入任务名称"
          />
        </a-form-item>

        <a-form-item label="自定义提示词" field="prompt">
          <a-textarea
            v-model="formData.prompt"
            :max-length="3000"
            :auto-size="{ minRows: 3, maxRows: 8 }"
            placeholder="请对以下文章内容进行摘要总结，用2-3句话提取关键信息和要点。摘要中请包含公众号名称、文章标题、文章链接和发布日期。"
            show-word-limit
            allow-clear
          />
          <template #extra>留空将使用默认提示词</template>
        </a-form-item>

        <a-form-item label="cron表达式" field="cron_exp" required>
          <a-space>
            <a-input
              v-model="formData.cron_exp"
              placeholder="请输入cron表达式"
              readonly
              style="width: 300px"
            />
            <a-button @click="showCronPicker = true">选择</a-button>
          </a-space>
          <template #extra>建议设置在凌晨低峰时段执行，如 0 2 * * *（每天凌晨2点）</template>
        </a-form-item>

        <a-form-item label="公众号" field="mps_id">
          <a-space>
            <a-input
              :model-value="(formData.mps_id || []).map((mp: any) => mp.id?.toString() || mp.toString()).join(',')"
              placeholder="请选择公众号，留空则对所有公众号生效"
              readonly
              style="width: 300px"
            />
            <a-button @click="showMpSelector = true">选择</a-button>
          </a-space>
        </a-form-item>

        <a-form-item label="状态" field="status">
          <a-radio-group v-model="formData.status" type="button">
            <a-radio :value="1">启用</a-radio>
            <a-radio :value="0">禁用</a-radio>
          </a-radio-group>
        </a-form-item>

        <a-form-item style="margin-top: 24px;">
          <a-space>
            <a-button html-type="submit" type="primary" :loading="loading">
              提交
            </a-button>
            <a-button @click="router.go(-1)">取消</a-button>
          </a-space>
        </a-form-item>
      </a-form>

      <!-- cron表达式选择器模态框 -->
      <a-modal
        v-model:visible="showCronPicker"
        title="选择cron表达式"
        :footer="false"
        width="800px"
      >
        <cronExpressionPicker
          ref="cronPickerRef"
          v-model="formData.cron_exp"
        />
        <template #footer>
          <a-button type="primary" @click="showCronPicker = false">确定</a-button>
        </template>
      </a-modal>

      <!-- 公众号选择器模态框 -->
      <a-modal
        v-model:visible="showMpSelector"
        title="选择公众号"
        :footer="false"
        width="800px"
      >
        <MpMultiSelect
          ref="mpSelectorRef"
          v-model="formData.mps_id"
        />
        <template #footer>
          <a-button type="primary" @click="showMpSelector = false">确定</a-button>
        </template>
      </a-modal>

      <a-divider />

      <a-alert type="info">
        <template #title>使用说明</template>
        <ul style="margin: 4px 0 0 0; padding-left: 16px; line-height: 2;">
          <li>此任务会自动遍历所选公众号的所有文章，调用大模型生成摘要</li>
          <li>已经生成过AI摘要的文章会自动跳过，避免重复生成</li>
          <li>请确保已在「大模型配置」页面配置好 API 地址和密钥</li>
          <li>建议将执行时间设置在凌晨低峰时段，避免影响正常使用</li>
          <li>创建/修改任务后需要点击「应用」按钮才会让定时任务生效</li>
        </ul>
      </a-alert>
    </div>
  </a-spin>
</template>

<style scoped>
.ai-summary-task-form {
  width: 90%;
  margin: 0 auto;
}

h2 {
  margin-bottom: 20px;
  color: var(--color-text-1);
}
</style>
