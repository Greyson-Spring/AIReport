<template>
  <a-layout-header>
    <a-menu
      mode="horizontal"
      :selected-keys="selectedKeys"
      @menu-item-click="handleMenuClick"
    >
      <!-- 订阅管理始终可见 -->
      <a-menu-item key="/">
        <template #icon>
          <icon-home />
        </template>
        订阅管理
      </a-menu-item>
      <template v-for="menu in filteredMenus" :key="menu.key">
        <a-menu-item>
          <template #icon>
            <component :is="menu.icon" />
          </template>
          {{ menu.label }}
        </a-menu-item>
      </template>
    </a-menu>
  </a-layout-header>
</template>

<script setup lang="ts">
import { ref, computed, watchEffect, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  IconWechat, IconExport, IconTag, IconNotification, IconFilter,
  IconList, IconStorage, IconShareExternal, IconLock,
  IconExclamationCircle, IconRobot, IconSettings, IconInfoCircle, IconUser, IconMessage
} from '@arco-design/web-vue/es/icon'
import TextIcon from '@/components/TextIcon.vue'
import { useUserPermissions } from '@/composables/useUserPermissions'

// 所有菜单项定义（不含订阅管理）
const allMenus = [
  { key: '/wechat-status', label: '授权管理', icon: IconWechat },
  { key: '/export/records', label: '导出记录', icon: IconExport },
  { key: '/tags', label: '标签管理', icon: IconTag },
  { key: '/message-tasks', label: '消息任务', icon: IconNotification },
  { key: '/filter-rules', label: '过滤规则', icon: IconFilter },
  { key: '/task-queue', label: '任务队列', icon: IconList },
  { key: '/cascade/feed-status', label: '公众号状态', icon: IconStorage },
  { key: '/cascade', label: '级联管理', icon: IconShareExternal },
  { key: '/access-keys', label: 'Access Key', icon: IconLock },
  { key: '/env-exception', label: '异常统计', icon: IconExclamationCircle },
  { key: '/llm-config', label: '大模型配置', icon: IconRobot },
  { key: '/ai-qa', label: 'AI问答', icon: IconMessage },
  { key: '/configs', label: '配置信息', icon: IconSettings },
  { key: '/sys-info', label: '系统信息', icon: IconInfoCircle },
  { key: '/user-management', label: '用户管理', icon: IconUser },
]

const { userRole, menuPermissions, loadPermissions } = useUserPermissions()

const router = useRouter()
const route = useRoute()
const selectedKeys = ref<string[]>(['/'])

const filteredMenus = computed(() => {
  if (userRole.value === 'admin') {
    return allMenus
  }
  if (!menuPermissions.value || menuPermissions.value.length === 0) {
    return []
  }
  return allMenus.filter(m => menuPermissions.value.includes(m.key))
})

watchEffect(() => {
  selectedKeys.value = [route.path]
})

const handleMenuClick = (key: string) => {
  if (route.path === key) return
  router.push(key).catch((err) => {
    if (!err.message?.includes('Avoided redundant navigation')) {
      console.error('路由导航失败:', err)
    }
  })
}

onMounted(() => {
  loadPermissions()
})
</script>