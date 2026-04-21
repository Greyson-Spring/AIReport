<template>
  <div style="padding: 20px;">
    <a-card title="用户管理">
      <template #extra>
        <a-button type="primary" @click="showAddModal">
          <template #icon><icon-plus /></template>
          添加用户
        </a-button>
      </template>

      <a-table :data="userList" :loading="loading" :pagination="false" row-key="username">
        <template #columns>
          <a-table-column title="用户名" data-index="username" />
          <a-table-column title="昵称" data-index="nickname" />
          <a-table-column title="邮箱" data-index="email" />
          <a-table-column title="角色" data-index="role">
            <template #cell="{ record }">
              <a-tag :color="record.role === 'admin' ? 'red' : 'blue'">{{ record.role === 'admin' ? '管理员' : '普通用户' }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="状态">
            <template #cell="{ record }">
              <a-tag :color="record.is_active ? 'green' : 'gray'">{{ record.is_active ? '启用' : '禁用' }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="菜单权限">
            <template #cell="{ record }">
              <a-space wrap :size="4">
                <a-tag v-for="key in (record.menu_permissions || [])" :key="key" size="small" color="arcoblue">
                  {{ menuLabelMap[key] || key }}
                </a-tag>
                <span v-if="record.role === 'admin'" style="color: var(--color-text-3); font-size: 12px;">全部权限</span>
                <span v-else-if="!record.menu_permissions?.length" style="color: var(--color-text-3); font-size: 12px;">无</span>
              </a-space>
            </template>
          </a-table-column>
          <a-table-column title="创建时间" data-index="created_at" />
          <a-table-column title="操作" :width="280">
            <template #cell="{ record }">
              <a-space>
                <a-button size="small" type="text" @click="showEditModal(record)">
                  <template #icon><icon-edit /></template>
                  编辑
                </a-button>
                <a-button size="small" type="text" @click="showResetPwdModal(record)">
                  <template #icon><icon-lock /></template>
                  重置密码
                </a-button>
                <a-popconfirm content="确认删除该用户？" @ok="handleDelete(record.username)">
                  <a-button size="small" type="text" status="danger" :disabled="record.role === 'admin'">
                    <template #icon><icon-delete /></template>
                    删除
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>

    <!-- 添加/编辑用户弹窗 -->
    <a-modal
      v-model:visible="formVisible"
      :title="isEdit ? '编辑用户' : '添加用户'"
      @ok="handleSubmit"
      :ok-loading="submitLoading"
      @cancel="formVisible = false"
      :width="600"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="用户名" :disabled="isEdit" required>
          <a-input v-model="form.username" :disabled="isEdit" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item v-if="!isEdit" label="密码" required>
          <a-input-password v-model="form.password" placeholder="请输入密码（至少6位）" />
        </a-form-item>
        <a-form-item label="邮箱">
          <a-input v-model="form.email" placeholder="请输入邮箱" />
        </a-form-item>
        <a-form-item label="角色">
          <a-select v-model="form.role">
            <a-option value="user">普通用户</a-option>
            <a-option value="admin">管理员</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="状态">
          <a-switch v-model="form.is_active" checked-text="启用" unchecked-text="禁用" />
        </a-form-item>
        <a-form-item v-if="form.role !== 'admin'" label="菜单权限">
          <div class="menu-perms-hint" style="margin-bottom: 8px; color: var(--color-text-3); font-size: 12px;">
            勾选后该用户可以看到对应的导航菜单（管理员默认拥有全部权限）
          </div>
          <a-checkbox-group v-model="form.menu_permissions" direction="vertical">
            <a-checkbox v-for="menu in allMenus" :key="menu.key" :value="menu.key">
              {{ menu.label }}
            </a-checkbox>
          </a-checkbox-group>
        </a-form-item>
        <a-form-item v-if="form.role !== 'admin'" label="按钮权限">
          <div class="menu-perms-hint" style="margin-bottom: 8px; color: var(--color-text-3); font-size: 12px;">
            勾选后该用户可以看到订阅管理页面中对应的操作按钮
          </div>
          <a-checkbox-group v-model="form.menu_permissions" direction="vertical">
            <a-checkbox v-for="btn in allButtons" :key="btn.key" :value="btn.key">
              {{ btn.label }}
            </a-checkbox>
          </a-checkbox-group>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 重置密码弹窗 -->
    <a-modal
      v-model:visible="resetPwdVisible"
      title="重置密码"
      @ok="handleResetPwd"
      :ok-loading="resetLoading"
      @cancel="resetPwdVisible = false"
    >
      <a-form layout="vertical">
        <a-form-item label="用户名">
          <a-input :model-value="resetTarget" disabled />
        </a-form-item>
        <a-form-item label="新密码" required>
          <a-input-password v-model="newPassword" placeholder="请输入新密码（至少6位）" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconPlus, IconEdit, IconDelete, IconLock } from '@arco-design/web-vue/es/icon'
import {
  getUserList,
  createUser,
  updateUser,
  deleteUser,
  resetUserPassword,
  type UserItem
} from '@/api/userManage'

// 所有可分配的菜单（不包含订阅管理）
const allMenus = [
  { key: '/wechat-status', label: '授权管理' },
  { key: '/export/records', label: '导出记录' },
  { key: '/tags', label: '标签管理' },
  { key: '/message-tasks', label: '消息任务' },
  { key: '/filter-rules', label: '过滤规则' },
  { key: '/task-queue', label: '任务队列' },
  { key: '/cascade/feed-status', label: '公众号状态' },
  { key: '/cascade', label: '级联管理' },
  { key: '/access-keys', label: 'Access Key' },
  { key: '/env-exception', label: '异常统计' },
  { key: '/llm-config', label: '大模型配置' },
  { key: '/ai-qa', label: 'AI问答' },
  { key: '/configs', label: '配置信息' },
  { key: '/sys-info', label: '系统信息' },
  { key: '/user-management', label: '用户管理' },
]

// 操作按钮权限
const allButtons = [
  { key: 'btn:ai-summary', label: 'AI摘要' },
  { key: 'btn:ai-report', label: 'AI报告生成' },
  { key: 'btn:ai-qa', label: 'AI问答' },
  { key: 'btn:export', label: '导出' },
  { key: 'btn:clean', label: '清理' },
  { key: 'btn:refresh-auth', label: '刷新授权' },
  { key: 'btn:subscribe', label: '订阅' },
  { key: 'btn:batch-delete', label: '批量删除' },
]

// 菜单 key → label 映射
const menuLabelMap: Record<string, string> = {}
allMenus.forEach(m => { menuLabelMap[m.key] = m.label })
allButtons.forEach(b => { menuLabelMap[b.key] = b.label })

const loading = ref(false)
const userList = ref<UserItem[]>([])
const formVisible = ref(false)
const isEdit = ref(false)
const submitLoading = ref(false)
const resetPwdVisible = ref(false)
const resetLoading = ref(false)
const resetTarget = ref('')
const newPassword = ref('')

const form = ref({
  username: '',
  password: '',
  email: '',
  role: 'user',
  is_active: true,
  menu_permissions: [] as string[]
})

const fetchUsers = async () => {
  loading.value = true
  try {
    const res: any = await getUserList()
    userList.value = res?.list || []
  } catch (e) {
    Message.error('获取用户列表失败')
  } finally {
    loading.value = false
  }
}

const showAddModal = () => {
  isEdit.value = false
  form.value = { username: '', password: '', email: '', role: 'user', is_active: true, menu_permissions: [] }
  formVisible.value = true
}

const showEditModal = (record: UserItem) => {
  isEdit.value = true
  form.value = {
    username: record.username,
    password: '',
    email: record.email || '',
    role: record.role || 'user',
    is_active: record.is_active,
    menu_permissions: record.menu_permissions || []
  }
  formVisible.value = true
}

const handleSubmit = async () => {
  if (!form.value.username) {
    Message.warning('请输入用户名')
    return
  }
  if (!isEdit.value && (!form.value.password || form.value.password.length < 6)) {
    Message.warning('密码不能少于6位')
    return
  }
  submitLoading.value = true
  try {
    if (isEdit.value) {
      await updateUser({
        username: form.value.username,
        email: form.value.email,
        role: form.value.role,
        is_active: form.value.is_active,
        menu_permissions: form.value.role === 'admin' ? [] : form.value.menu_permissions
      })
      Message.success('用户已更新')
    } else {
      await createUser({
        username: form.value.username,
        password: form.value.password,
        email: form.value.email,
        role: form.value.role,
        is_active: form.value.is_active,
        menu_permissions: form.value.role === 'admin' ? [] : form.value.menu_permissions
      })
      Message.success('用户已创建')
    }
    formVisible.value = false
    fetchUsers()
  } catch (e: any) {
    Message.error(e?.message || '操作失败')
  } finally {
    submitLoading.value = false
  }
}

const handleDelete = async (username: string) => {
  try {
    await deleteUser(username)
    Message.success('用户已删除')
    fetchUsers()
  } catch (e: any) {
    Message.error(e?.message || '删除失败')
  }
}

const showResetPwdModal = (record: UserItem) => {
  resetTarget.value = record.username
  newPassword.value = ''
  resetPwdVisible.value = true
}

const handleResetPwd = async () => {
  if (!newPassword.value || newPassword.value.length < 6) {
    Message.warning('密码不能少于6位')
    return
  }
  resetLoading.value = true
  try {
    await resetUserPassword(resetTarget.value, newPassword.value)
    Message.success('密码已重置')
    resetPwdVisible.value = false
  } catch (e: any) {
    Message.error(e?.message || '重置失败')
  } finally {
    resetLoading.value = false
  }
}

onMounted(() => {
  fetchUsers()
})
</script>
