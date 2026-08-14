<template>
  <div class="account-pool-page">
    <a-page-header title="账号池管理" subtitle="管理微信读书采集账号" :show-back="false">
      <template #extra>
        <a-space>
          <a-button @click="loadStatus">刷新</a-button>
          <a-button type="primary" @click="handleAdd">添加账号</a-button>
        </a-space>
      </template>
    </a-page-header>

    <!-- 加载中 -->
    <a-spin :loading="loading" style="width: 100%;">
      <!-- 账号列表 -->
      <div v-if="accounts.length > 0" style="display: flex; flex-wrap: wrap; gap: 16px;">
        <a-card v-for="acc in accounts" :key="acc.port" :bordered="true" style="width: 340px;">
          <template #title>
            <a-space>
              <span>账号 #{{ acc.port }}</span>
              <a-tag :color="tagColor(acc)">{{ tagText(acc) }}</a-tag>
            </a-space>
          </template>

          <!-- 状态信息 -->
          <div style="font-size: 13px; line-height: 1.8;">
            <div>Chrome 端口: {{ acc.port }} ({{ acc.chrome_alive ? '运行中' : '未运行' }})</div>
            <div>状态: {{ acc.status }}</div>
            <div v-if="acc.last_error">最近错误: <b style="color: red;">{{ acc.last_error }}</b></div>
            <div v-if="acc.error_count">错误次数: {{ acc.error_count }}</div>
          </div>

          <!-- 错误解决方法 -->
          <a-alert
            v-if="solutions[String(acc.last_error)]"
            type="warning"
            :title="`错误码 ${acc.last_error} 解决方法`"
            :content="solutions[String(acc.last_error)]"
            style="margin-top: 10px;"
          />

          <!-- 二维码(用于扫码登录) -->
          <div style="margin-top: 12px; text-align: center;">
            <img
              :src="qrUrl(acc.port)"
              style="width: 160px; height: 160px; border: 1px solid #eee;"
              alt="扫码登录二维码"
            />
            <div style="font-size: 12px; color: #999; margin-top: 4px;">若需登录, 用微信扫码</div>
          </div>

          <!-- 操作 -->
          <div style="margin-top: 12px; display: flex; gap: 8px;">
            <a-button type="text" @click="qrUrl(acc.port)" style="display: none;"></a-button>
            <a-button size="small" @click="loadStatus">检查</a-button>
            <a-button size="small" status="danger" @click="handleRemove(acc)">移除账号</a-button>
          </div>
        </a-card>
      </div>

      <!-- 空状态 -->
      <a-empty v-else :description="'暂无账号, 点击「添加账号」创建'" style="margin-top: 60px;" />
    </a-spin>

    <!-- 添加成功提示 -->
    <a-modal v-model:visible="addModalVisible" title="添加账号" :footer="false" width="380">
      <template v-if="lastAddedPort">
        <p>新账号已启动(端口 {{ lastAddedPort }})，请用微信扫码登录微信读书：</p>
        <div style="text-align: center; margin: 12px 0;">
          <img :src="qrUrl(lastAddedPort)" style="width: 220px; height: 220px; border: 1px solid #eee;" />
        </div>
        <div style="text-align: center; margin-bottom: 8px;">
          <a-button size="small" @click="handleRefreshQr">二维码过期了？点这里刷新</a-button>
        </div>
        <p style="color: #999; font-size: 12px;">二维码有效期短，请扫码后尽快确认。关闭本窗口不影响登录。</p>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getAccountPoolStatus, addAccount, refreshAccountQr, removeAccount } from '@/api/accountPool'

const loading = ref(false)
const accounts = ref<any[]>([])
const addModalVisible = ref(false)
const lastAddedPort = ref<number | null>(null)
const qrVersion = ref(0)

// 错误码 → 解决方法
const solutions: Record<string, string> = {
  '-2014': '微信读书请求频率过高(限流)。降低抓取频率 / 暂停几小时让限流冷却, 不要反复重试。',
  '-2012': '微信读书会话超时。请重新扫码登录该账号。',
  '-2010': '微信读书用户不存在(登录失效)。请重新扫码登录该账号。',
  '-2041': '被微信读书反爬拦截, 需要验证码(暂不支持自动解)。建议降低频率或稍后再试。',
  'NO_READER_PAGE': '没有阅读器页。请刷新该账号的微信读书阅读器页。',
  'chrome_down': 'Chrome 未运行或无响应。请检查该账号的 Chrome 服务。',
  'CDP_RECV_FAIL': 'Chrome 页面无响应。请刷新该账号的阅读器页。',
  'CDP_CONNECT_FAIL': '无法连接 Chrome。请检查该账号的 Chrome 服务。',
  'EVAL_ERROR': '页面执行出错。请刷新该账号的阅读器页。'
}

const tagColor = (acc: any) => {
  if (!acc.chrome_alive) return 'gray'
  if (acc.status === 'ok') return 'green'
  if (acc.status === 'error') return 'red'
  return 'orange'
}
const tagText = (acc: any) => {
  if (!acc.chrome_alive) return 'Chrome未运行'
  if (acc.status === 'ok') return '正常'
  if (acc.status === 'error') return `错误 ${acc.last_error}`
  return acc.status
}

const qrUrl = (port: number) => {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  // 加时间戳强制刷新, 让新Chrome的二维码加载出来后自动显示
  return `${base}api/v1/wx/account-pool/qr?port=${port}&t=${qrVersion.value}`
}

const loadStatus = async () => {
  loading.value = true
  try {
    const res: any = await getAccountPoolStatus()
    const data = res?.data?.data || res?.data || {}
    // 转成数组
    accounts.value = Object.keys(data).map(k => data[k])
  } catch (e: any) {
    Message.error('获取账号池状态失败: ' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

const handleAdd = async () => {
  try {
    const res: any = await addAccount()
    const data = res?.data?.data || res?.data || {}
    if (data.err) {
      Message.error('添加失败: ' + data.err)
      return
    }
    lastAddedPort.value = data.port
    addModalVisible.value = true
    qrVersion.value++  // 加载一次二维码(接口内部会导航+点登录确保新鲜)
    loadStatus()
  } catch (e: any) {
    Message.error('添加失败: ' + (e?.message || e))
  }
}

const handleRefreshQr = async () => {
  if (!lastAddedPort.value) return
  try {
    await refreshAccountQr(lastAddedPort.value)
    qrVersion.value++
    Message.success('二维码已刷新, 请尽快扫码')
  } catch (e: any) {
    Message.error('刷新失败: ' + (e?.message || e))
  }
}

const handleRemove = async (acc: any) => {
  try {
    await removeAccount(acc.port)
    Message.success('账号已移除')
    loadStatus()
  } catch (e: any) {
    Message.error('移除失败: ' + (e?.message || e))
  }
}

onMounted(loadStatus)
</script>

<style scoped>
.account-pool-page {
  padding: 0 20px 20px;
}
</style>
