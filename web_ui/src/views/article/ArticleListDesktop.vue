<template>
  <a-spin :loading="fullLoading" tip="正在刷新..." size="large" style="width: 100%; height: 100%;">
    <a-layout class="article-list">
      
      <a-layout-sider :width="300"
        :style="{ background: '#fff', padding: '0', borderRight: '1px solid #eee', display: 'flex', flexDirection: 'column', border: 0 }">
        <a-card :bordered="false" title="公众号"
          :headStyle="{ padding: '12px 16px', borderBottom: '1px solid #eee', background: '#fff', zIndex: 1, border: 0 }">
          <!-- 具名插槽#extra：卡片右上角额外操作区域 -->
          <template #extra>
            <a-space>
              <a-dropdown>
                <!-- 订阅按钮 -->
                <a-button type="primary">
                  <template #icon><icon-plus /></template>
                  订阅
                  <icon-down />
                </a-button>
                <!-- 订阅里面的选项 -->
                <template #content>
                  <a-doption @click="showAddModal"><template #icon><icon-plus /></template>添加公众号</a-doption>
                  <a-doption @click="showAddFeaturedArticleModal"><template #icon><icon-link /></template>添加精选文章</a-doption>
                  <a-doption @click="exportMPS"><template #icon><icon-export /></template>导出公众号</a-doption>
                  <a-doption @click="importMPS"><template #icon><icon-import /></template>导入公众号</a-doption>
                  <a-doption @click="exportOPML"><template #icon><icon-share-external /></template>导出OPML</a-doption>
                </template>
              </a-dropdown>

              <!-- 在分组按钮后面添加 -->
              <a-dropdown>
                <a-button type="outline">
                  <template #icon><icon-folder /></template>
                  分类
                  <icon-down />
                </a-button>
                <template #content>
                  <a-doption @click="showCreateFolderModal">
                    <template #icon><icon-plus /></template>
                    新建分类
                  </a-doption>
                </template>
              </a-dropdown>

            </a-space>
          </template>

          <div style="display: flex; flex-direction: column;; background: #fff">
            <!-- 搜索框 -->
            <div style="margin-bottom: 12px;">
              <a-input-search 
                v-model="mpSearchText" 
                placeholder="搜索公众号名称" 
                @search="handleMpSearch" 
                @keyup.enter="handleMpSearch"
                allow-clear 
                size="small" />
            </div>
            <!-- 选项卡 -->
            <div style="margin-bottom: 8px; padding: 0 8px;">
              <a-radio-group v-model="mpFilterType" type="button" size="small" style="width: 100%;">
                <a-radio value="all" style="flex: 1; text-align: center;">全部</a-radio>
                <a-radio value="active" style="flex: 1; text-align: center;">启用</a-radio>
                <a-radio value="disabled" style="flex: 1; text-align: center;">停用</a-radio>
              </a-radio-group>
            </div>
            <!-- 统一列表循环 -->
            <div style="flex: 1; overflow-y: auto; padding: 8px 0;">
              
              <!-- ========== 1. 系统项区域 ========== -->
              <div class="system-section">
                <div 
                  v-for="item in systemItems" 
                  :key="item.id"
                  class="list-item"
                  :class="{ active: activeItem.type === 'system' && activeItem.id === item.id }"
                  @click="handleLeftItemClick(item)"
                >
                  <icon-file v-if="item.icon === 'icon-file'" />
                  <icon-star v-else />
                  <span style="flex: 1;">{{ item.name }}</span>
                  <!-- <span class="item-count">({{ item.count }})</span> -->
                </div>
              </div>
              
              <!-- 分隔线 -->
              <div class="section-divider"></div>
              
              <!-- ========== 2. 自定义文件夹区域 ========== -->
              <div class="folders-section" v-if="folderTree.length > 0">
                <div 
                  v-for="folder in folderTree" 
                  :key="folder.id"
                  class="folder-wrapper"
                >
                  <!-- 文件夹本身 -->
                  <div 
                    class="list-item folder-item"
                    :class="{ 
                      active: activeItem.type === 'folder' && activeItem.id === folder.id,
                      'drag-over': dragOverFolderId === folder.id
                    }"
                    @click="handleLeftItemClick(folder)"
                    @dragover="(e) => onDragOver(e, folder.id)"
                    @dragleave="onDragLeave"
                    @drop="(e) => onDropToFolder(e, folder.id)"
                  >
                    <span class="folder-arrow" @click.stop="toggleFolder(folder.id)">
                      <icon-right v-if="!folder.expanded" />
                      <icon-down v-else />
                    </span>
                    <icon-folder v-if="!folder.isEditing"/>
                    <!-- 编辑模式：输入框 -->
                    <input 
                      v-if="folder.isEditing"
                      v-model="folder.editName"
                      type="text"
                      class="folder-edit-input"
                      @blur="saveFolderName(folder)"
                      @keyup.enter="saveFolderName(folder)"
                      @keyup.esc="cancelEditFolder(folder)"
                      @click.stop
                      autofocus
                    />
                    <!-- 显示模式：名称 -->
                    <span 
                      v-else
                      style="flex: 1;" 
                      @dblclick.stop="startEditFolder(folder)"
                    >
                      {{ folder.name }}
                    </span>
                    <!-- 删除按钮(始终占位; 选中时可见, 不改变布局/行高) -->
                    <a-button
                      :style="{
                        visibility: (activeItem.type === 'folder' && activeItem.id === folder.id && !folder.isEditing) ? 'visible' : 'hidden',
                        height: '20px', minHeight: '20px', lineHeight: '20px', padding: '0 4px', flexShrink: 0
                      }"
                      size="mini"
                      type="text"
                      status="danger"
                      @click.stop="confirmDeleteFolder(folder)"
                    >
                      <template #icon><icon-delete /></template>
                    </a-button>
                    <!-- 数量显示：只在非编辑状态下显示 -->
                    <span  v-if="!folder.isEditing" class="item-count">({{ folder.feeds.length }})</span>
                  </div>
                  
                  <!-- 文件夹内的公众号列表(每页5个) -->
                  <div v-if="folder.expanded" class="folder-children">
                    <div
                      v-for="feed in getFolderPagedFeeds(folder)"
                      :key="feed.id"
                      class="list-item"
                      :class="{ active: activeItem.type === 'mp' && activeItem.id === feed.id }"
                      draggable="true"
                      @click="handleLeftItemClick(feed)"
                      @dragstart="(e) => onDragStart(e, feed.id)"
                      @dragend="onDragEnd"
                    >
                      <img :src="Avatar(feed.avatar || '')" class="avatar-small" />
                      <span style="flex: 1;" :style="{ opacity: feed.status === 0 ? 0.5 : 1 }">{{ feed.name }}</span>
                      <!-- 删除禁用按钮 -->
                      <div v-if="activeItem.type === 'mp' && activeItem.id === feed.id && canManageMp(feed.id)" style="display: flex; gap: 4px;">
                        <a-button size="mini" type="text" status="danger" @click.stop="deleteMp(feed.id)">
                          <template #icon><icon-delete /></template>
                        </a-button>
                        <a-button size="mini" type="text" @click.stop="copyMpId(feed.id)">
                          <template #icon><icon-copy /></template>
                        </a-button>
                        <a-button size="mini" type="text" @click.stop="toggleMpStatus(feed.id, feed.status === 1 ? 0 : 1)">
                          <template #icon>
                            <icon-stop v-if="feed.status === 1" />
                            <icon-play-arrow v-else />
                          </template>
                        </a-button>
                      </div>
                    </div>
                    <!-- 文件夹内部分页(每页5个) -->
                    <a-pagination
                      v-if="folder.feeds.length > 5"
                      :total="folder.feeds.length"
                      :current="folderPageMap[folder.id] || 1"
                      :page-size="5"
                      simple
                      @change="(page: number) => handleFolderPageChange(folder.id, page)"
                      style="margin: 8px 0 8px 24px;"
                    />
                  </div>
                </div>
              </div>

              <!-- ========== 3. 未分类公众号区域 ========== -->
              <div class="unassigned-section"
                  @dragover.prevent
                  @drop="onDropToUnassigned">
                <div class="section-title">未分类公众号</div>
                
                <!-- 有公众号时显示列表 -->
                <div v-if="pagedUnassignedMpList.length > 0">
                  <div
                    v-for="mp in pagedUnassignedMpList"
                    :key="mp.id"
                    class="list-item"
                    :class="{ active: activeItem.type === 'mp' && activeItem.id === mp.id }"
                    draggable="true"
                    @click="handleLeftItemClick(mp)"
                    @dragstart="(e) => onDragStart(e, mp.id)"
                    @dragend="onDragEnd"
                  >
                    <img :src="Avatar(mp.avatar || '')" class="avatar-small" />
                    <span style="flex: 1;" :style="{ opacity: mp.status === 0 ? 0.5 : 1 }">{{ mp.name }}</span>
                    <!-- 删除禁用按钮:只在选中时显示 -->
                    <div v-if="activeItem.type === 'mp' && activeItem.id === mp.id && canManageMp(mp.id)" style="display: flex; gap: 4px;">
                      <a-button size="mini" type="text" status="danger" @click.stop="deleteMp(mp.id)">
                        <template #icon><icon-delete /></template>
                      </a-button>
                      <a-button size="mini" type="text" @click.stop="copyMpId(mp.id)">
                        <template #icon><icon-copy /></template>
                      </a-button>
                      <a-button size="mini" type="text" @click.stop="toggleMpStatus(mp.id, mp.status === 1 ? 0 : 1)">
                        <template #icon>
                          <icon-stop v-if="mp.status === 1" />
                          <icon-play-arrow v-else />
                        </template>
                      </a-button>
                    </div>
                  </div>
                </div>
                
                <!-- 没有公众号时显示提示 -->
                <div v-else class="empty-drop-tip">
                  <icon-export />
                  <span>拖拽公众号到此可移出文件夹</span>
                </div>
              </div>
            </div>
            <!-- 未分类公众号分页: 固定在侧边栏底部, 列表滚动也不影响使用; 页码紧凑自动省略(1 2 3 ... N) -->
            <div style="flex-shrink: 0; padding: 8px; border-top: 1px solid var(--color-neutral-3); background: #fff;">
              <a-pagination
                :total="mpPagination.total"
                :current="mpPagination.current"
                :page-size="mpPagination.pageSize"
                @change="handleMpPageChange"
                :show-total="true"
                :show-page-size="false"
                :show-jumper="false"
                size="small"
                :buffer-size="2"
                style="width: 100%;"
              />
            </div>
          </div>
        </a-card>
      </a-layout-sider>

      <a-layout-content style="padding: 20px;">
        <a-page-header :title="activeFeed ? activeFeed.name : '全部'" :subtitle="'管理您的公众号订阅内容'" :show-back="false">
          <template #extra>
            <a-space>
              <span style="font-size: 12px; color: var(--color-text-3);">{{ issourceUrl ? '原链接' : '内链' }}</span>
              <a-switch 
                v-model="issourceUrl" 
                size="small" 
                style="margin: 0 8px;">
              </a-switch>


              <a-button v-if="hasPermission('btn:ai-summary')" @click="handleAISummary">
                <template #icon><icon-robot /></template>
                AI摘要
              </a-button>
              <AISummaryModal ref="aiSummaryModal" />


              <a-button v-if="hasPermission('btn:ai-report')" @click="handleAIReport">
                <template #icon><icon-file /></template>
                AI报告生成
              </a-button>

              <a-button v-if="hasPermission('btn:ai-qa')" @click="handleAIQA">
                <template #icon><icon-message /></template>
                AI问答
              </a-button>

              <a-button v-if="hasPermission('btn:export')" @click="handleExportShow()">
                <template #icon><icon-export /></template>
                导出
              </a-button>
              <ExportModal ref="exportModal"  />
              <a-button @click="refresh" v-if="activeFeed?.id != '' && activeFeed?.id !== FEATURED_MP_ID">
                <template #icon><icon-refresh /></template>
                刷新
              </a-button>
              <a-dropdown v-if="hasPermission('btn:clean')">
                <a-button v-if="activeFeed?.id == ''">
                  <template #icon><icon-delete /></template>
                  清理
                  <icon-down />
                </a-button>
                <template #content>
                  <a-doption @click="clear_articles">
                    <template #icon> <TextIcon text="E" /></template>
                    清理无效文章
                  </a-doption>
                  <a-doption @click="clear_duplicate_article">
                    <template #icon> <TextIcon text="C" /></template>
                    清理重复文章
                  </a-doption>
                </template>
              </a-dropdown>
              <a-button v-if="hasPermission('btn:refresh-auth')" @click="handleAuthClick">
                <template #icon><icon-scan /></template>
                刷新授权
              </a-button>
              <a-dropdown v-if="hasPermission('btn:subscribe')">
                <a-button>
                  <template #icon>
                    <IconWifi />
                  </template>
                  订阅
                  <icon-down />
                </a-button>
                <template #content>
                  <a-doption @click="rssFormat = 'atom'; openRssFeed()"><template #icon>
                      <TextIcon text="atom" />
                    </template>ATOM</a-doption>
                  <a-doption @click="rssFormat = 'rss'; openRssFeed()"><template #icon>
                      <TextIcon text="rss" />
                    </template>RSS</a-doption>
                  <a-doption @click="rssFormat = 'json'; openRssFeed()"><template #icon>
                      <TextIcon text="json" />
                    </template>JSON</a-doption>
                  <a-doption @click="rssFormat = 'md'; openRssFeed()"><template #icon>
                      <TextIcon text="md" />
                    </template>Markdown</a-doption>
                  <a-doption @click="rssFormat = 'txt'; openRssFeed()"><template #icon>
                      <TextIcon text="txt" />
                    </template>Text</a-doption>
                </template>
              </a-dropdown>
              <a-button v-if="hasPermission('btn:batch-delete')" type="primary" status="danger" @click="handleBatchDelete" :disabled="!selectedRowKeys.length">
                <template #icon><icon-delete /></template>
                批量删除
              </a-button>
            </a-space>
          </template>
        </a-page-header>

        <a-card style="border:0">
          <a-alert type="success" closable>{{ activeFeed?.mp_intro || "请选择一个公众号码进行管理,搜索文章后再点击订阅会有惊喜哟！！！" }}</a-alert>
          <div class="search-bar">
            <a-input-search class="search-input" v-model="searchText" placeholder="搜索文章标题" @search="handleSearch" @keyup.enter="handleSearch"
              allow-clear />
            <a-checkbox class="favorite-filter" :model-value="onlyFavorite" @change="handleFavoriteFilterChange">仅显示已收藏</a-checkbox>
            <a-dropdown trigger="click" position="bl">
              <a-button size="small">
                <template #icon><icon-settings /></template>
                列设置
              </a-button>
              <template #content>
                <a-doption v-for="col in allColumnOptions" :key="col.key" @click.stop>
                  <a-checkbox 
                    :model-value="visibleColumns.includes(col.key)" 
                    @change="(val) => toggleColumn(col.key, val)"
                    :disabled="col.required"
                  >
                    {{ col.label }}
                  </a-checkbox>
                </a-doption>
              </template>
            </a-dropdown>
          </div>
          <a-table :columns="columns" :data="articles" :loading="loading" :pagination="pagination"
            :scroll="{ x: '100%' }"
            :row-selection="{
            type: 'checkbox',
            showCheckedAll: true,
            width: 50,
            fixed: true,
            checkStrictly: true,
            onlyCurrent: false
          }" row-key="id" @page-change="handlePageChange" @page-size-change="handlePageSizeChange" v-model:selectedKeys="selectedRowKeys">
            <template #status="{ record }">
              <a-tag :color="statusColorMap[record.status]">
                {{ statusTextMap[record.status] }}
              </a-tag>
            </template>
            <template #actions="{ record }">
              <a-space>
                <a-button type="text" @click="viewArticle(record)" :title="record.id">
                  <template #icon><icon-eye /></template>
                </a-button>
                <a-button type="text" @click="toggleFavoriteStatus(record)" :title="record.is_favorite === 1 ? '取消收藏' : '收藏'">
                  <template #icon>
                    <icon-star-fill v-if="record.is_favorite === 1" />
                    <icon-star v-else />
                  </template>
                </a-button>
                <a-button
                  type="text"
                  :loading="refreshingArticleIds.includes(String(record.id))"
                  @click="refreshSingleArticle(record)"
                >
                  <template #icon><icon-refresh /></template>
                </a-button>
                <a-button type="text" status="danger" @click="deleteArticle(record.id)">
                  <template #icon><icon-delete /></template>
                </a-button>
              </a-space>
            </template>
          </a-table>


          <a-modal v-model:visible="refreshModalVisible" title="刷新设置">
            <a-form :model="refreshForm" :rules="refreshRules">
              <a-form-item label="起始页" field="startPage">
                <a-input-number v-model="refreshForm.startPage" :min="1" />
              </a-form-item>
              <a-form-item label="结束页" field="endPage">
                <a-input-number v-model="refreshForm.endPage" :min="1" />
              </a-form-item>
            </a-form>
            <template #footer>
              <a-button @click="refreshModalVisible = false">取消</a-button>
              <a-button type="primary" @click="handleRefresh">确定</a-button>
            </template>
          </a-modal>
          <a-modal v-model:visible="featuredArticleModalVisible" title="添加精选文章">
            <a-form>
              <a-form-item label="文章链接">
                <div class="featured-url-input-wrapper">
                  <a-input
                    v-model="featuredArticleUrl"
                    placeholder="请输入微信公众号文章链接"
                    allow-clear
                  />
                  <div class="featured-url-example">eg：https://mp.weixin.qq.com/s/xxxxx</div>
                </div>
              </a-form-item>
            </a-form>
            <template #footer>
              <a-button @click="featuredArticleModalVisible = false">取消</a-button>
              <a-button type="primary" @click="handleAddFeaturedArticle">添加</a-button>
            </template>
          </a-modal>
          <a-modal id="article-model" v-model:visible="articleModalVisible"
            placement="left" :footer="false" :fullscreen="false" @before-close="resetScrollPosition">
            <h2 id="topreader">{{ currentArticle.title }}</h2>
            <div style="margin-top: 20px; color: var(--color-text-3); text-align: left">
              <a-link :href="currentArticle.url" target="_blank">查看原文</a-link>
              更新时间 ：{{ currentArticle.time }}
            <a-link @click="viewArticle(currentArticle,-1)" target="_blank">上一篇 </a-link>
            <a-space/>
            <a-link @click="viewArticle(currentArticle,1)" target="_blank">下一篇 </a-link>
            </div>
            <div ref="shadowContainer" style="width: 100%; height: auto;"></div>

            <div style="margin-top: 20px; color: var(--color-text-3); text-align: right">
              {{ currentArticle.time }}
            </div>
          </a-modal>
          <!-- 新建文件夹弹窗 -->
          <a-modal v-model:visible="createFolderModalVisible" title="新建文件夹" @ok="handleCreateFolder">
            <a-form>
              <a-form-item label="文件夹名称">
                <a-input 
                  v-model="newFolderName" 
                  placeholder="请输入文件夹名称"
                  @keyup.enter="handleCreateFolder"
                />
              </a-form-item>
            </a-form>
          </a-modal>

        </a-card>
      </a-layout-content>
    </a-layout>
  </a-spin>
</template>

<script setup lang="ts">
import { Avatar } from '@/utils/constants'
import { translatePage, setCurrentLanguage } from '@/utils/translate';
import { ref, onMounted, h, nextTick, watch, computed, resolveComponent } from 'vue'
import axios from 'axios'
import { IconFolder,IconRight,IconFile, IconExport, IconAtt, IconApps,IconDelete, IconEdit, IconEye, IconRefresh, IconScan, IconWeiboCircleFill, IconWifi, IconCode, IconCheck, IconClose, IconStop, IconPlayArrow, IconCopy, IconPlus, IconDown, IconImport, IconShareExternal, IconStar, IconStarFill, IconLink, IconSettings } from '@arco-design/web-vue/es/icon'
import { getArticles, deleteArticle as deleteArticleApi, ClearArticle, ClearDuplicateArticle, getArticleDetail, getRefreshArticleTaskStatus, refreshArticle as refreshArticleApi, toggleArticleFavoriteStatus, toggleArticleReadStatus } from '@/api/article'
import { ExportOPML, ExportMPS, ImportMPS } from '@/api/export'
import ExportModal from '@/components/ExportModal.vue'
import AISummaryModal from '@/components/AISummaryModal.vue'

import { addFeaturedArticle, getFeaturedArticleTaskStatus, getSubscriptions, UpdateMps, toggleMpStatus as toggleMpStatusApi } from '@/api/subscription'
import { inject } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { formatDateTime, formatTimestamp } from '@/utils/date'
import router from '@/router'
import { deleteMpApi } from '@/api/subscription'
import TextIcon from '@/components/TextIcon.vue'
import { useUserPermissions } from '@/composables/useUserPermissions'
import { Space } from '@arco-design/web-vue'
const { hasPermission, loadPermissions } = useUserPermissions()
import { ProxyImage } from '@/utils/constants'
import { 
  createFolder, 
  getFolderList, 
  deleteFolder, 
  addFeedsToFolder, 
  getFolderFeeds,
  removeFeedFromFolder,
  updateFolder
} from '@/api/folder';

const articles = ref([])
const FEATURED_MP_ID = 'MP_WXS_FEATURED_ARTICLES'
const FEATURED_MP_NAME = '精选文章'
const loading = ref(false)
// const mpList = ref([])
const mpLoading = ref(false)      // 公众号列表加载状态
const activeMpId = ref('')        // 当前选中的公众号ID，''表示全部
const activeFolderId = ref(null)  // 当前选中的文件夹ID
const exportModal = ref()
const aiSummaryModal = ref()

// ========== 新增：左侧列表数据结构 ==========
// 1. 系统项
const systemItems = ref([
  { id: '', name: '全部', type: 'system', icon: 'icon-file', count: 0 },
  { id: 'MP_WXS_FEATURED_ARTICLES', name: '精选文章', type: 'system', icon: 'icon-star', count: 0 }
])

// 2. 文件夹树（每个文件夹包含子公众号）
const folderTree = ref([])

// 3. 未分类的公众号列表
const unassignedMpList = ref([])

// 4. 当前选中的项
const activeItem = ref({ type: '', id: null })

// 5. 拖拽相关
let draggingFeedId: string | null = null
const dragOverFolderId = ref<number | null>(null)
// ========= 以上是左侧列表的新增数据结构 ==========

const selectedRowKeys = ref([])
const mpPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showPageSize: false,
  showJumper: false,
  showTotal: true,
  pageSizeOptions: [5, 10, 15]
})
const mpFilterType = ref('all') // 'active' | 'disabled' | 'all'
// 未分类公众号分页显示(按当前页截取)
const pagedUnassignedMpList = computed(() => {
  const start = (mpPagination.value.current - 1) * mpPagination.value.pageSize
  return unassignedMpList.value.slice(start, start + mpPagination.value.pageSize)
})
const searchText = ref('')
const filterStatus = ref('')
const mpSearchText = ref('')
const onlyFavorite = ref(false)
const featuredArticleModalVisible = ref(false)
const featuredArticleUrl = ref('')
// ========== 文件夹相关 ==========
const createFolderModalVisible = ref(false)
const newFolderName = ref('')


// 显示新建弹窗
const showCreateFolderModal = () => {
  newFolderName.value = ''
  createFolderModalVisible.value = true
}

// 创建文件夹（调用后端API）
const handleCreateFolder = async () => {
  if (!newFolderName.value.trim()) {
    Message.warning('请输入文件夹名称')
    return
  }
  
  try {
    const res = await createFolder(newFolderName.value.trim())
    if (res && res.id) {
      await buildLeftSidebarData('')  // ← 改这里
      createFolderModalVisible.value = false
      newFolderName.value = ''
      Message.success('文件夹创建成功')
    } else {
      Message.error('创建失败')
    }
  } catch (error: any) {
    console.error('创建文件夹失败:', error)
    Message.error(error || '创建失败')
  }
}

// 确认删除文件夹
const confirmDeleteFolder = (folder: any) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除文件夹"${folder.name}"吗？删除文件夹会删除其中的公众号。`,
    okText: '确认删除',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteFolder(folder.id)
        await buildLeftSidebarData('')  //  改
        
        if (activeFolderId.value === folder.id) {
          activeFolderId.value = null
          activeMpId.value = ''
          await fetchArticles()
        }
        Message.success(`已删除文件夹"${folder.name}"`)
      } catch (error: any) {
        console.error('删除文件夹失败:', error)
        Message.error(error || '删除失败')
      }
    }
  })
}
// 开始编辑文件夹名称
const startEditFolder = (folder) => {
  folder.isEditing = true
  folder.editName = folder.name
}

// 保存文件夹名称

let isSaving = false  // 防止重复保存

const saveFolderName = async (folder) => {
  if (!folder.isEditing || isSaving) return
  
  const newName = folder.editName?.trim()
  if (!newName || newName === folder.name) {
    folder.isEditing = false
    return
  }
  
  isSaving = true
  try {
    await updateFolder(folder.id, newName)
    folder.name = newName
    Message.success('文件夹名称修改成功')
  } catch (error) {
    console.error('修改文件夹名称失败:', error)
    Message.error(error?.response?.data?.detail || '修改失败')
  } finally {
    folder.isEditing = false
    isSaving = false
  }
}

// 取消编辑
const cancelEditFolder = (folder) => {
  folder.isEditing = false
}
// ========== 构建左侧数据 ==========
const buildLeftSidebarData = async (searchKeyword = '') => {
  try {
    console.log('开始构建左侧数据...')
    
    // 1. 并行获取所有文件夹和所有公众号（不分页，假设不会超过100个）
    const [folderListRes, allFeedsRes] = await Promise.all([
      getFolderList(),
      getSubscriptions({ page: 0, pageSize: 1000 })
    ])


    // 2. 处理文件夹列表
    let backendFolders = []
    if (Array.isArray(folderListRes)) {
      backendFolders = folderListRes
    } else if (folderListRes?.data && Array.isArray(folderListRes.data)) {
      backendFolders = folderListRes.data
    }
    console.log('backendFolders 示例:', backendFolders[0])
    console.log('backendFolders 完整数据:', backendFolders)


    // 3. 处理所有公众号
    // getSubscriptions 返回的格式是 { list: [], total: 0, page: {...} }
    let allFeeds = []
    if (allFeedsRes?.list) {
      // 先过滤掉系统项（精选文章）
      let filteredFeeds = allFeedsRes.list.filter(item => item.id !== FEATURED_MP_ID)
      // 3.1 根据启用/停用选项卡筛选状态：根据 mpFilterType 筛选状态
      if (mpFilterType.value === 'active') {
        filteredFeeds = filteredFeeds.filter(item => item.status === 1)
      } else if (mpFilterType.value === 'disabled') {
        filteredFeeds = filteredFeeds.filter(item => item.status === 0)
      }
      // 'all' 时不过滤
      // allFeeds = filteredFeeds
      allFeeds = filteredFeeds.map(feed => ({
        id: feed.id,
        name: feed.mp_name || feed.name,  // 优先使用 mp_name
        status: feed.status,
        avatar: feed.mp_cover || feed.avatar || ''
      }))
    }

    // 4. 构建文件夹树
    const folderTreeData = []
    const allArchivedFeedIds = new Set() // 记录所有已在文件夹中的公众号ID，用于排除未分类列表

    for (const folder of backendFolders) {
      // 4.1 获取该文件夹内的所有公众号
      let feedsInFolder = []
      try {
        const feedsRes = await getFolderFeeds(folder.id)
        console.log(`文件夹 ${folder.name} 的 feedsRes:`, feedsRes)
        if (feedsRes?.data?.feeds) {
          feedsInFolder = feedsRes.data.feeds
        } else if (feedsRes?.feeds) {
          feedsInFolder = feedsRes.feeds
        }
      } catch (error) {
        console.error(`获取文件夹 ${folder.name} 内的公众号失败:`, error)
      }

      //4.2记录这个文件夹内的所有公众号ID（用于构建未分类列表，不受筛选影响）
      feedsInFolder.forEach(feed => {
        allArchivedFeedIds.add(feed.id)
      })
      // 4.3 根据搜索关键词过滤文件夹内的公众号（公众号名称包含关键词才显示）
      let filteredFeedsInFolder = feedsInFolder
      if (searchKeyword) {
        filteredFeedsInFolder = filteredFeedsInFolder.filter(feed => 
          feed.name && feed.name.toLowerCase().includes(searchKeyword.toLowerCase())
        )
      }
      // 4.4 根据启用/停用选项卡筛选状态：根据 mpFilterType 筛选状态
      if (mpFilterType.value === 'active') {
        filteredFeedsInFolder = filteredFeedsInFolder.filter(feed => feed.status === 1)
      } else if (mpFilterType.value === 'disabled') {
        filteredFeedsInFolder = filteredFeedsInFolder.filter(feed => feed.status === 0)
      }
      // 👇 关键修改：只要文件夹内有匹配的公众号，就显示该文件夹
      // 即使 filteredFeedsInFolder 为空，如果搜索词为空也要显示文件夹
      const shouldShowFolder = !searchKeyword || filteredFeedsInFolder.length > 0

      // 4.5 构建文件夹树（只使用过滤后的数据）
      folderTreeData.push({
        id: folder.id,
        name: folder.name,
        type: 'folder',     // 用于区分系统项、文件夹和公众号
        expanded: searchKeyword ? true : false,  // 搜索时自动展开
        feedCount: filteredFeedsInFolder.length,
        feeds: filteredFeedsInFolder.map(feed => ({
          id: feed.id,
          name: feed.name,
          type: 'mp',
          avatar: feed.avatar || '',
          status: feed.status   // || 1 默认启用
        })),
        isEditing: false,      // 是否处于编辑模式
        editName: folder.name  // 临时存储编辑中的名称
      })
    }

    folderTree.value = folderTreeData

    // 5. 构建未分类公众号列表（不在任何文件夹中的公众号）
    let unassigned = allFeeds.filter(feed => !allArchivedFeedIds.has(feed.id))
    console.log('过滤前的 unassigned 数量:', unassigned.length)
    console.log('过滤前的 unassigned 名称:', unassigned.map(f => f.name))
    // ========== 5.1 根据搜索关键词过滤未分类公众号 ==========
    if (searchKeyword) {
      unassigned = unassigned.filter(feed =>
        feed.name && feed.name.toLowerCase().includes(searchKeyword.toLowerCase())
      )
      console.log('过滤后的 unassigned 数量:', unassigned.length)
      console.log('过滤后的 unassigned 名称:', unassigned.map(f => f.name))
    }

    unassignedMpList.value = unassigned.map(feed => ({
      id: feed.id || feed.mp_id,
      name: feed.name || feed.mp_name,
      type: 'mp',
      avatar: feed.avatar || feed.mp_cover || '',
      status: feed.status
    }))
    // 更新未分类公众号分页
    mpPagination.value.total = unassignedMpList.value.length
    mpPagination.value.current = 1

    console.log('左侧数据构建完成:', {
      folders: folderTree.value.length,
      archivedFeeds: allArchivedFeedIds.size,
      unassignedFeeds: unassignedMpList.value.length
    })

  } catch (error) {
    console.error('构建左侧数据失败:', error)
  }
}
  
// ========== 拖拽功能 ==========
const onDragStart = (event, feedId) => {
  draggingFeedId = feedId
  event.dataTransfer.setData('text/plain', feedId)
  event.dataTransfer.effectAllowed = 'move'
  event.target.classList?.add('dragging')
}

const onDragEnd = (event) => {
  draggingFeedId = null
  dragOverFolderId.value = null
  event.target.classList?.remove('dragging')
}

const onDragOver = (event, folderId) => {
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dragOverFolderId.value = folderId
}

const onDragLeave = () => {
  dragOverFolderId.value = null
}

const onDropToFolder = async (event, folderId) => {
  event.preventDefault()
  dragOverFolderId.value = null

  const feedId = draggingFeedId || event.dataTransfer.getData('text/plain')
  if (!feedId) return

  try {
    await addFeedsToFolder(folderId, [feedId])
    Message.success('公众号已添加到文件夹')
    await buildLeftSidebarData('')  // 刷新左侧数据

    if (activeItem.value.type === 'mp' && activeItem.value.id === feedId) {
      activeItem.value = { type: '', id: null }
      articles.value = []
    }
  } catch (error) {
    console.error('添加失败:', error)
    Message.error(error?.response?.data?.detail || '添加失败')
  } finally {
    draggingFeedId = null
  }
}
const onDropToUnassigned = async (event) => {
  event.preventDefault()
  
  const feedId = draggingFeedId || event.dataTransfer.getData('text/plain')
  if (!feedId) return
  
  // 查找这个公众号当前在哪个文件夹
  let sourceFolderId = null
  let sourceFeed = null
  for (const folder of folderTree.value) {
    const feed = folder.feeds.find(f => f.id === feedId)
    if (feed) {
      sourceFolderId = folder.id
      sourceFeed = { ...feed }  // 复制一份，保留数据
      break
    }
  }
  
  if (!sourceFolderId) {
    Message.info('公众号已在未分类区域')
    return
  }
  
  try {
    await removeFeedFromFolder(sourceFolderId, feedId)
    
    // 手动更新本地数据（立即生效，不用等刷新）
    // 1. 从文件夹中移除
    const folder = folderTree.value.find(f => f.id === sourceFolderId)
    if (folder) {
      const index = folder.feeds.findIndex(f => f.id === feedId)
      if (index !== -1) folder.feeds.splice(index, 1)
    }
    
    // 2. 添加到未分类列表（避免重复）
    if (sourceFeed && !unassignedMpList.value.some(f => f.id === feedId)) {
      unassignedMpList.value.push(sourceFeed)
    }
    // 3. 同步更新未分类分页的"共N条", 否则要刷新页面才变化
    mpPagination.value.total = unassignedMpList.value.length
    
    Message.success('公众号已移出文件夹')
    
    // 如果当前选中的是被移动的公众号，清空选中
    if (activeItem.value.type === 'mp' && activeItem.value.id === feedId) {
      activeItem.value = { type: '', id: null }
      articles.value = []
    }
    
  } catch (error) {
    console.error('移出失败:', error)
    Message.error(error?.response?.data?.detail || '移出失败')
  } finally {
    draggingFeedId = null
  }
}

// ========== 文件夹展开/收起 ==========
const toggleFolder = (folderId) => {
  const folder = folderTree.value.find(f => f.id === folderId)
  if (folder) {
    folder.expanded = !folder.expanded
  }
}

// ========== 点击处理 ==========
const handleLeftItemClick = async (item) => {
  // 1. 检查是否有正在编辑的文件夹，如果有，先保存
  const editingFolder = folderTree.value.find(f => f.isEditing === true)
  if (editingFolder) {
    // 先保存正在编辑的文件夹
    await saveFolderName(editingFolder)
    // 如果保存后 item 可能发生变化，重新获取
    if (item.id === editingFolder.id) {
      // 如果点击的就是正在编辑的文件夹，保存后直接返回，避免重复处理
      return
    }
  }
  // 2. 处理点击事件
  activeItem.value = { type: item.type, id: item.id }

  if (item.type === 'system') {
    activeMpId.value = item.id
    activeFolderId.value = null
    activeFeed.value = { name: item.name, id: item.id, mp_intro: '' }
    pagination.value.current = 1
    await fetchArticles()
  } 
  else if (item.type === 'folder') {
    activeFolderId.value = item.id
    activeMpId.value = null
    activeFeed.value = { 
      name: item.name, 
      id: item.id, 
      mp_intro: `包含 ${item.feeds.length} 个公众号` 
    }
    pagination.value.current = 1
    await fetchArticlesByFolder(item)
  }
  else if (item.type === 'mp') {
    activeMpId.value = item.id
    activeFolderId.value = null
    activeFeed.value = item
    pagination.value.current = 1
    await fetchArticles()
  }
}

// ========== 获取文件夹内文章 ==========
const fetchArticlesByFolder = async (folder) => {
  if (!folder || !folder.id) {
    articles.value = []
    pagination.value.total = 0
    return
  }

  if ((folder.feeds || []).length === 0) {
    articles.value = []
    pagination.value.total = 0
    Message.info(`"${folder.name}" 文件夹暂无公众号`)
    return
  }

  // 一次性按 folder_id 查询(后端做分页), 不再逐个公众号请求
  await fetchArticles()
}
// ========= 获取文章列表 ==========


const pagination = ref({
  current: 1, // 当前页码
  pageSize: 10,
  total: 0,
  showTotal: true,
  showJumper: true,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50, 100]
})

const statusTextMap = {
  published: '已发布',
  draft: '草稿',
  deleted: '已删除'
}

const statusColorMap = {
  published: 'green',
  draft: 'orange',
  deleted: 'red'
}

// 原创状态映射
const copyrightTextMap: Record<number, string> = {
  0: '否',
  1: '是',
  11: '是',
  12: '是',
  13: '是',
  14: '是'
}

const copyrightColorMap: Record<number, string> = {
  0: 'gray',
  1: 'green',
  11: 'purple',
  12: 'orange',
  13: 'red',
  14: 'cyan'
}

// 展示类型映射
const itemShowTypeTextMap: Record<number, string> = {
  0: '图文',
  1: '图片',
  2: '音频',
  3: '视频',
  10: '纯文字',
  11: '文字+图片'
}

const itemShowTypeColorMap: Record<number, string> = {
  0: 'green',
  1: 'purple',
  2: 'orange',
  3: 'red',
  10: 'gray',
  11: 'cyan'
}

// 发布类型映射
const publishTypeTextMap: Record<number, string> = {
  1: '发布',
  2: '转载',
  3: '草稿'
}

const publishTypeColorMap: Record<number, string> = {
  1: 'green',
  2: 'blue',
  3: 'orange'
}

// 列配置选项
const allColumnOptions = [
  { key: 'is_read', label: '已阅', required: true },
  { key: 'pic_url', label: '题图', required: false },
  { key: 'title', label: '文章标题', required: true },
  { key: 'mp_id', label: '公众号', required: false },
  { key: 'has_content', label: '正文', required: false },
  { key: 'copyright_stat', label: '原创', required: false },
  { key: 'item_show_types', label: '类型', required: false },
  { key: 'created_at', label: '更新时间', required: false },
  { key: 'publish_time', label: '发布时间', required: false },
  { key: 'actions', label: '操作', required: true }
]

// 默认显示的列
const defaultVisibleColumns = ['is_read', 'pic_url', 'title', 'mp_id', 'created_at', 'publish_time', 'actions']

// 从 localStorage 读取列配置
const getStoredColumns = (): string[] => {
  try {
    const stored = localStorage.getItem('articleListVisibleColumns')
    if (stored) {
      return JSON.parse(stored)
    }
  } catch {}
  return defaultVisibleColumns
}

const visibleColumns = ref<string[]>(getStoredColumns())

// 切换列显示状态
const toggleColumn = (key: string, checked: boolean) => {
  const option = allColumnOptions.find(o => o.key === key)
  if (option?.required) return
  
  if (checked) {
    if (!visibleColumns.value.includes(key)) {
      visibleColumns.value = [...visibleColumns.value, key]
    }
  } else {
    visibleColumns.value = visibleColumns.value.filter(k => k !== key)
  }
  localStorage.setItem('articleListVisibleColumns', JSON.stringify(visibleColumns.value))
}

// 计算动态宽度 - 不再需要，标题列自适应
// const getDynamicTitleWidth = () => { ... }

const columns = computed(() => {
  const allColumns = [
    {
      title: '已阅',
      dataIndex: 'is_read',
      width: 60,
      render: ({ record }) => {
        const isRead = record.is_read === 1;
        return h('div', {
          style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: isRead ? '#52c41a' : 'var(--color-text-3)'
          },
          onClick: () => toggleReadStatus(record)
        }, [
          h(isRead ? IconCheck : IconClose, {
            style: { marginRight: '2px' }
          }),
          h('span', {
            style: { fontSize: '12px' }
          }, isRead ? '' : '')
        ]);
      }
    },
    {
      title: '题图',
      dataIndex: 'pic_url',
      width: 80,
      align: 'center',
      render: ({ record }) => {
        if (!record.pic_url) return h('span', { style: { color: 'var(--color-text-4)' } }, '-')
        const Popover = resolveComponent('a-popover')
        return h(Popover, {
          trigger: 'hover',
          position: 'right',
          'content-style': { padding: '4px' }
        }, {
          default: () => h('img', {
            src: record.pic_url,
            style: {
              width: '60px',
              height: '40px',
              objectFit: 'cover',
              borderRadius: '4px',
              cursor: 'pointer'
            },
            onClick: () => viewArticle(record)
          }),
          content: () => h('img', {
            src: record.pic_url,
            style: {
              maxWidth: '300px',
              maxHeight: '200px',
              borderRadius: '4px'
            }
          })
        })
      }
    },
    {
      title: '文章标题',
      dataIndex: 'title',
      ellipsis: true,
      render: ({ record }) => h('div', {}, [
        h('a', {
          href: issourceUrl.value ? record.url || '#' : "/views/article/" + record.id,
          title: record.title,
          target: '_blank',
          style: {
            color: 'var(--color-text-1)',
            textDecoration: record.is_read === 1 ? 'line-through' : 'none',
            opacity: record.is_read === 1 ? 0.7 : 1
          }
        }, record.title),
        record.description ? h('div', {
          style: {
            fontSize: '12px',
            color: 'var(--color-text-3)',
            marginTop: '4px',
            lineHeight: '1.4',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            '-webkit-line-clamp': '2',
            '-webkit-box-orient': 'vertical'
          }
        }, record.description) : null
      ])
    },
    {
      title: '公众号',
      dataIndex: 'mp_id',
      width: 90,
      ellipsis: true,
      render: ({ record }) => {
        
        const mp = [...unassignedMpList.value, ...folderTree.value.flatMap(f => f.feeds)].find(item => item.id === record.mp_id);
        return h('a', {
          style: {
            color: 'var(--color-link)',
            cursor: 'pointer',
            textDecoration: 'none'
          },
          onClick: (e: MouseEvent) => {
            e.preventDefault()
            handleMpClick(record.mp_id)
          }
        }, record.mp_name || mp?.name || record.mp_id)
      }
    },
    {
      title: '正文',
      dataIndex: 'has_content',
      width: 60,
      align: 'center',
      render: ({ record }) => {
        const hasContent = record.has_content === 1
        return h('a-tag', {
          style: {
            color: hasContent ? 'green' : 'gray',
            fontSize: '12px'
          },
          size: 'small'
        }, hasContent ? '有' : '无')
      }
    },
    {
      title: '原创',
      dataIndex: 'copyright_stat',
      width: 60,
      align: 'center',
      render: ({ record }) => {
        const stat = record.copyright_stat ?? 0
        return h('a-tag', {
          color: copyrightColorMap[stat] ,
          size: 'small'
        }, copyrightTextMap[stat] || '未知')
      }
    },
    {
      title: '类型',
      dataIndex: 'item_show_types',
      width: 60,
      align: 'center',
      render: ({ record }) => {
        const showType = record.item_show_types ?? 0
        return h('a-tag', {
          color: itemShowTypeColorMap[showType] || 'gray',
          size: 'small'
        }, itemShowTypeTextMap[showType] || '图文')
      }
    },
    {
      title: '更新时间',
      dataIndex: 'created_at',
      width: 130,
      render: ({ record }) => h('span',
        { style: { color: 'var(--color-text-3)', fontSize: '12px' } },
        formatDateTime(record.created_at)
      )
    },
    {
      title: '发布时间',
      dataIndex: 'publish_time',
      width: 130,
      render: ({ record }) => h('span',
        { style: { color: 'rgb(var(--color-text-3))', fontSize: '12px' } },
        formatTimestamp(record.publish_time)
      )
    },
    {
      title: '操作',
      dataIndex: 'actions',
      width: 140,
      align: 'center',
      fixed: 'right',
      slotName: 'actions'
    }
  ]

  return allColumns.filter(col => visibleColumns.value.includes(col.dataIndex as string))
})

const handleMpPageChange = (page: number, pageSize?: number) => {
  mpPagination.value.current = page
  // 防御: 某些情况下 pageSize 可能没传, 避免 slice(NaN) 导致列表为空
  if (pageSize && pageSize > 0) {
    mpPagination.value.pageSize = pageSize
  }
}

// ===== 文件夹内部分页 (每页5个) =====
const folderPageMap = ref<Record<string, number>>({})
const getFolderPagedFeeds = (folder: any) => {
  // 搜索时显示全部匹配(不截断), 避免匹配的号被分页藏起来
  if (mpSearchText.value.trim()) {
    return folder.feeds || []
  }
  const page = folderPageMap.value[folder.id] || 1
  const size = 5
  const start = (page - 1) * size
  return (folder.feeds || []).slice(start, start + size)
}
const handleFolderPageChange = (folderId: number, page: number) => {
  folderPageMap.value[folderId] = page
}

const handleMpSearch = () => {
  // mpPagination.value.current = 1
  // fetchMpList()
  console.log('搜索功能已启用')
  buildLeftSidebarData(mpSearchText.value.trim())
}

// 监听筛选类型变化，重置分页并重新请求
// watch(mpFilterType, () => {
//   mpPagination.value.current = 1
//   // fetchMpList()
//   console.log('分页功能暂未实现，等待后续优化')
// })
// 监听筛选类型变化，重新构建左侧数据
watch(mpFilterType, () => {
  // buildLeftSidebarData()  // 重新构建左侧数据
  buildLeftSidebarData(mpSearchText.value.trim())  // 保留搜索关键词

})

const rssFormat = ref('atom')
const activeFeed = ref({
  id: "",
  name: "全部",
}) // 当前选中的公众号/文件夹/系统项对象，包含 id、name、mp_intro 等字段
const canManageMp = (mpId: string) => mpId !== '' && mpId !== FEATURED_MP_ID

const showAddFeaturedArticleModal = () => {
  featuredArticleUrl.value = ''
  featuredArticleModalVisible.value = true
}

const handleAddFeaturedArticle = async () => {
  const url = featuredArticleUrl.value.trim()
  if (!url) {
    Message.warning('请输入文章链接')
    return
  }
  if (!url.includes('mp.weixin.qq.com/s/')) {
    Message.warning('请输入有效的公众号文章链接')
    return
  }

  try {
    const res = await addFeaturedArticle({ url })
    const taskId = res?.task_id
    Message.success(res?.message || '已开始添加/抓取，请稍后刷新查看结果')
    featuredArticleModalVisible.value = false
    if (!taskId) {
      return
    }

    for (let i = 0; i < 15; i++) {
      await new Promise((resolve) => setTimeout(resolve, 2000))
      try {
        const task = await getFeaturedArticleTaskStatus(taskId)
        if (task?.status === 'success') {
          Message.success(task?.message || '精选文章添加成功')
          // await fetchMpList()
          handleMpClick(FEATURED_MP_ID)
          return
        }
        if (task?.status === 'failed') {
          Message.error(task?.message || '添加精选文章失败')
          return
        }
      } catch (error) {
        console.error('查询精选文章任务失败:', error)
      }
    }

    Message.info('导入任务仍在执行，请稍后手动刷新查看结果')
  } catch (error) {
    Message.error(String(error || '添加精选文章失败'))
  }
}

const handleMpClick = (mpId: string) => {
  activeMpId.value = mpId
  pagination.value.current = 1
  activeFolderId.value = null  // 👈 添加这行，清空文件夹选中
  // activeFeed.value = mpList.value.find(item => item.id === activeMpId.value)
  const allMps = [...unassignedMpList.value, ...folderTree.value.flatMap(f => f.feeds)]
activeFeed.value = allMps.find(item => item.id === activeMpId.value) || { name: '全部', id: activeMpId.value, mp_intro: '' }
  console.log(activeFeed.value)

  fetchArticles()
}

const fetchArticles = async () => {
  loading.value = true
  try {
    // 判断是否选择了“精选文章”
    const isFeatured = activeMpId.value === FEATURED_MP_ID

    console.log('请求参数:', {
      page: pagination.value.current - 1,
      pageSize: pagination.value.pageSize,
      search: searchText.value,
      status: filterStatus.value,
      mp_id: activeMpId.value,
      only_favorite: onlyFavorite.value
    })

    const res = await getArticles({
      page: pagination.value.current - 1,
      pageSize: pagination.value.pageSize,
      search: searchText.value,
      status: filterStatus.value,
      mp_id: isFeatured ? undefined : activeMpId.value,  // 精选文章时不按 mp_id 筛选
      folder_id: activeFolderId.value || undefined,       // 文件夹视图: 按文件夹筛选
      only_favorite: isFeatured || onlyFavorite.value   // 精选文章时强制只显示收藏的
    })

    // 确保数据包含必要字段
    articles.value = (res.list || []).map(item => ({
      ...item,
      mp_name: item.mp_name || item.account_name || '未知公众号',
      publish_time: item.publish_time || item.create_time || '-',
      url: item.url || "https://mp.weixin.qq.com/s/" + item.id,
      is_favorite: item.is_favorite === 1 ? 1 : 0
    }))
    pagination.value.total = res.total || 0
  } catch (error) {
    console.error('获取文章列表错误:', error)
    Message.error(error)
  } finally {
    loading.value = false
  }
}
const issourceUrl = ref(false)

// 从 localStorage 读取 issourceUrl 值
const initIssourceUrl = () => {
  const savedValue = localStorage.getItem('issourceUrl')
  if (savedValue !== null) {
    issourceUrl.value = savedValue === 'true'
  }
}

// 监听 issourceUrl 变化并保存到 localStorage
watch(issourceUrl, (newValue) => {
  localStorage.setItem('issourceUrl', newValue.toString())
}, { immediate: false })
const handlePageChange = (page: number) => {
  console.log('分页事件触发:', { page })
  pagination.value.current = page
  fetchArticles()
}

const handlePageSizeChange = (pageSize: number) => {
  console.log('页面大小改变:', { pageSize })
  pagination.value.pageSize = pageSize
  pagination.value.current = 1 // 切换页面大小时重置到第一页
  fetchArticles()
}

const handleSearch = () => {
  pagination.value.current = 1
  fetchArticles()
}

const handleFavoriteFilterChange = (value: boolean | (string | number | boolean)[]) => {
  onlyFavorite.value = Array.isArray(value) ? value.length > 0 : Boolean(value)
  pagination.value.current = 1
  fetchArticles()
}

const wechatAuthQrcodeRef = ref()
const showAuthQrcode = inject('showAuthQrcode') as () => void
const handleAuthClick = () => {
  showAuthQrcode()
}

const exportOPML = async () => {
  try {
    const response = await ExportOPML();
    const blob = new Blob([response], { type: 'application/xml' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'rss_feed.opml';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (error) {
    console.error('导出OPML失败:', error);
    Message.error(error?.message || '导出OPML失败');
  }
};
const exportMPS = async () => {
  try {
    const res = await ExportMPS();
    const data = (res as any).data ?? res;
    const blob = data instanceof Blob
      ? data
      : new Blob([data], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '公众号列表.csv';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (error: any) {
    Message.error(error?.message || '导出公众号失败');
  }
};

const importMPS = async () => {
  try {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      const response = await ImportMPS(formData);
      Message.info(response?.message || "导入成功");
    };
    input.click();
  } catch (error: any) {
    Message.error(typeof error === 'string' ? error : (error?.detail?.message || error?.message || '导入公众号失败'));
  }
};

const openRssFeed = () => {
  const format = ['rss', 'atom', 'json', 'md', 'txt'].includes(rssFormat.value)
    ? rssFormat.value
    : 'atom'
  let search = ""
  if (searchText.value != "") {
    search = "/search/" + searchText.value;
  }
  if (!activeMpId.value) {
    window.open(`/feed${search}/all.${format}`, '_blank')
    return
  }
  // const activeMp = mpList.value.find(item => item.id === activeMpId.value)
  const allMps = [...unassignedMpList.value, ...folderTree.value.flatMap(f => f.feeds)]
  const activeMp = allMps.find(item => item.id === activeMpId.value)
  if (activeMp) {
    window.open(`/feed${search}/${activeMpId.value}.${format}`, '_blank')
  }
}

const resetScrollPosition = () => {
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
}

const fullLoading = ref(false)

const refreshModalVisible = ref(false)
const refreshForm = ref({
  startPage: 0,
  endPage: 1
})
const refreshRules = {
  startPage: [{ required: true, message: '请输入开始页码' }],
  endPage: [{ required: true, message: '请输入结束页码' }]
}

const showRefreshModal = () => {
  refreshModalVisible.value = true
}

const handleRefresh = () => {
  fullLoading.value = true
  UpdateMps(activeMpId.value, {
    start_page: refreshForm.value.startPage,
    end_page: refreshForm.value.endPage
  }).then(() => {
    Message.success('刷新成功')
    refreshModalVisible.value = false
  }).finally(() => {
    fullLoading.value = false
  })
  fetchArticles()
}
const clear_articles = () => {
  fullLoading.value = true
  ClearArticle().then((res) => {
    Message.success(res?.message || '清理成功')
    refreshModalVisible.value = false
  }).finally(() => {
    fullLoading.value = false
  })
  fetchArticles()
}
const clear_duplicate_article = () => {
  fullLoading.value = true
  ClearDuplicateArticle().then((res) => {
    Message.success(res?.message || '清理成功')
    refreshModalVisible.value = false
  }).finally(() => {
    fullLoading.value = false
  })
  fetchArticles()
}

const refresh = () => {
  showRefreshModal()
}

const showAddModal = () => {
  router.push('/add-subscription')
}

const handleAddSuccess = () => {
  fetchArticles()
}
 const processedContent = (record: any) => {
 return ProxyImage(record.content)
 }
const viewArticle = async (record: any, action_type: number = 0) => {
  loading.value = true
  try {
    // console.log(record)
    const article = await getArticleDetail(record.id,action_type)
    currentArticle.value = {
      id: article.id,
      title: article.title,
      content: processedContent(article),
      time: formatDateTime(article.created_at),
      url: article.url
    }
    articleModalVisible.value = true
    window.location="#topreader"
    
    // 创建或更新 Shadow DOM
    await nextTick()
    createShadowHost()
    
    // 自动标记为已读（仅在查看当前文章时，不是上一篇/下一篇）
    if (action_type === 0 && record.is_read !== 1) {
      await toggleReadStatus(record)
    }
  } catch (error) {
    console.error('获取文章详情错误:', error)
    Message.error(error)
  } finally {
    loading.value = false
  }
}
const currentArticle = ref({
  title: '',
  content: '',
  time: '',
  url: ''
})
const articleModalVisible = ref(false)
const shadowContainer = ref()
const refreshingArticleIds = ref<string[]>([])

const deleteArticle = (id: number) => {
  Modal.confirm({
    title: '确认删除',
    content: '确定要删除该文章吗？删除后将无法恢复。',
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      await deleteArticleApi(id);
      Message.success('删除成功');
      fetchArticles();
    },
    onCancel: () => {
      Message.info('已取消删除操作');
    }
  });
}

const pollRefreshArticleTask = async (taskId: string) => {
  for (let i = 0; i < 15; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    try {
      const task = await getRefreshArticleTaskStatus(taskId)
      if (task?.status === 'success') {
        Message.success(task?.message || '文章刷新成功')
        await fetchArticles()
        return
      }
      if (task?.status === 'failed') {
        Message.error(task?.message || '文章刷新失败')
        return
      }
    } catch (error) {
      console.error('查询文章刷新任务失败:', error)
    }
  }

  Message.info('刷新任务仍在执行，请稍后手动刷新列表查看结果')
}

const refreshSingleArticle = async (record: any) => {
  const articleId = String(record.id)
  if (refreshingArticleIds.value.includes(articleId)) {
    return
  }

  refreshingArticleIds.value = [...refreshingArticleIds.value, articleId]
  try {
    const res = await refreshArticleApi(record.id)
    const taskId = res?.task_id
    Message.success(res?.message || '已开始刷新，请稍后查看')
    if (taskId) {
      await pollRefreshArticleTask(taskId)
    }
  } catch (error) {
    console.error('刷新文章失败:', error)
    Message.error(String(error || '刷新文章失败'))
  } finally {
    refreshingArticleIds.value = refreshingArticleIds.value.filter((id) => id !== articleId)
  }
}

const handleBatchDelete = () => {
  Modal.confirm({
    title: '确认批量删除',
    content: `确定要删除选中的${selectedRowKeys.value.length}篇文章吗？删除后将无法恢复。`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        await Promise.all(selectedRowKeys.value.map(id => deleteArticleApi(id)));
        Message.success(`成功删除${selectedRowKeys.value.length}篇文章`);
        selectedRowKeys.value = [];
        fetchArticles();
      } catch (error) {
        Message.error('删除部分文章失败');
      }
    },
    onCancel: () => {
      Message.info('已取消批量删除操作');
    }
  });
}

const handleExportShow = async () => {
  let mp_id=activeFeed.value?.id
  let ids=selectedRowKeys.value
  let mp_name=activeFeed.value?.name || activeFeed.value?.mp_name || '全部'
  exportModal.value.show(mp_id,ids,mp_name)
}

const handleAISummary = () => {
  const ids = selectedRowKeys.value
  if (!ids || ids.length === 0) {
    Message.warning('请先勾选要摘要的文章')
    return
  }
  aiSummaryModal.value.show(ids.map(String))
}
// ai报告传入参数和跳转
const handleAIReport = () => {
  // 判断当前选中的是什么类型
  const activeItemType = activeItem.value?.type
  const activeItemId = activeItem.value?.id
  
  let source = 'all'
  let mpId = ''
  let mpName = ''
  let folderId = ''
  let folderName = ''
  
  if (activeItemType === 'system') {
    // 系统项：可能是「全部」或「精选文章」
    if (activeItemId === '') {
      // 全部
      source = 'all'
      mpId = ''
      mpName = '全部'
    } else if (activeItemId === 'MP_WXS_FEATURED_ARTICLES') {
      // 精选文章（全站范围）
      source = 'favorite'
      mpId = ''
      mpName = '精选文章'
    }
  } 
  else if (activeItemType === 'folder') {
    // 文件夹：传文件夹ID
    source = 'folder'
    folderId = String(activeItemId)
    // 获取文件夹名称
    const folder = folderTree.value.find(f => f.id === activeItemId)
    folderName = folder?.name || '文件夹'
    mpName = folderName
  } 
  else if (activeItemType === 'mp') {
    // 单个公众号
    source = 'mp'
    mpId = String(activeItemId)
    // 获取公众号名称
    let mp = unassignedMpList.value.find(m => String(m.id) === String(activeItemId))
    if (!mp) {
      for (const folder of folderTree.value) {
        mp = folder.feeds.find(f => String(f.id) === String(activeItemId))
        if (mp) break
      }
    }
    mpName = mp?.name || activeFeed.value?.name || ''
  }
  
  // 跳转到AI报告页面
  router.push({ 
    path: '/ai-report', 
    query: { 
      mpId,
      mpName,
      source,
      folder_id: folderId,      // 改成 folder_id
      folder_name: folderName   // 改成 folder_name
    } 
  })
}

const handleAIQA = () => {
  const mpId = activeFeed.value?.id || ''
  const mpName = activeFeed.value?.name || activeFeed.value?.mp_name || '全部'
  router.push({ path: '/ai-qa', query: { mpId, mpName } })
}


onMounted(async () => {
  console.log('组件挂载，开始获取数据')
  await loadPermissions()
  initIssourceUrl()
  
  // 构建左侧数据
  await buildLeftSidebarData('')
  
  // 默认获取文章列表（全部）
  activeMpId.value = ''
  await fetchArticles()
  
  console.log('✅ ArticleListDesktop.vue 已加载，分组功能已启用')
})


// const fetchMpList = async () => {
//   mpLoading.value = true
//   try {
//     // 根据筛选类型确定 status 参数
//     let statusParam: number | undefined = undefined
//     if (mpFilterType.value === 'active') {
//       statusParam = 1
//     } else if (mpFilterType.value === 'disabled') {
//       statusParam = 0
//     }
//     // 'all' 时不传 status 参数

//     // 选择"全部"时，请求少2条（因为会添加"全部"选项，后端也会添加"精选文章"）
//     const adjustedPageSize = mpFilterType.value === 'all' && !mpSearchText.value
//       ? mpPagination.value.pageSize - 2
//       : mpPagination.value.pageSize

//     const res = await getSubscriptions({
//       page: mpPagination.value.current - 1,
//       pageSize: adjustedPageSize,
//       kw: mpSearchText.value,
//       status: statusParam
//     })

//     mpList.value = res.list.map(item => ({
//       id: item.id || item.mp_id,
//       name: item.name || item.mp_name,
//       avatar: item.avatar || item.mp_cover || '',
//       mp_intro: item.mp_intro || item.mp_intro || '',
//       article_count: item.article_count || 0,
//       status: item.status ?? 1
//     }))
//     // 只在筛选全部且无搜索时添加'全部'选项
//     if (mpFilterType.value === 'all' && !mpSearchText.value) {
//       mpList.value.unshift({
//         id: '',
//         name: '全部',
//         avatar: '/static/logo.svg',
//         mp_intro: '显示所有公众号文章',
//         article_count: res.total || 0,
//         status: 1
//       });
//     }
//     mpPagination.value.total = res.total || 0
//   } catch (error) {
//     console.error('获取公众号列表错误:', error)
//   } finally {
//     mpLoading.value = false
//   }
// }

const copyMpId = async (mpId: string) => {
  try {
    await navigator.clipboard.writeText(mpId);
    Message.success('MP ID 已复制到剪贴板');
  } catch (error) {
    // 如果 clipboard API 不可用，使用传统方法
    const textArea = document.createElement('textarea');
    textArea.value = mpId;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      Message.success('MP ID 已复制到剪贴板');
    } catch (err) {
      Message.error('复制失败，请手动复制');
      console.error('复制失败:', err);
    }
    document.body.removeChild(textArea);
  }
}

const deleteMp = async (mpId: string) => {
  if (!canManageMp(mpId)) return
  
  Modal.confirm({
    title: '确认删除',
    content: '确定要删除该订阅号吗？删除后将无法恢复。',
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteMpApi(mpId)
        Message.success('订阅号删除成功')
        
        // 重新构建左侧数据
        await buildLeftSidebarData('')
        
        // 如果删除的是当前选中的公众号，清空选中状态
        if (activeItem.value.type === 'mp' && activeItem.value.id === mpId) {
          activeItem.value = { type: '', id: null }
          activeMpId.value = ''
          await fetchArticles()
        }
      } catch (error) {
        console.error('删除订阅号失败:', error)
        Message.error('删除订阅号失败，请稍后重试')
      }
    }
  })
}

const toggleMpStatus = async (mpId: string, newStatus: number) => {
  if (!canManageMp(mpId)) return
  
  try {
    await toggleMpStatusApi(mpId, newStatus)
    Message.success(newStatus === 0 ? '公众号已禁用' : '公众号已启用')
    
    // 重新构建左侧数据（刷新状态显示）
    await buildLeftSidebarData('')
    
  } catch (error) {
    console.error('更新公众号状态失败:', error)
    Message.error('更新公众号状态失败')
  }
}

const importArticles = () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;

    try {
      const content = await file.text();
      const data = JSON.parse(content);
      // 这里应该调用API导入数据
      Message.success(`成功导入${data.length}篇文章`);
    } catch (error) {
      console.error('导入文章失败:', error);
      Message.error('导入失败，请检查文件格式');
    }
  };
  input.click();
};

const exportArticles = () => {
  if (!articles.value.length) {
    Message.warning('没有文章可导出');
    return;
  }

  const data = JSON.stringify(articles.value, null, 2);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `articles_${activeMpId.value || 'all'}_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  Message.success('导出成功');
};

// 创建 Shadow DOM 隔离容器
const createShadowHost = () => {
  if (!shadowContainer.value) return;
  
  // 清空容器
  shadowContainer.value.innerHTML = '';
  
  // 创建 Shadow Host
  const shadowHost = document.createElement('div');
  shadowHost.style.width = '100%';
  shadowHost.style.height = 'auto';
  
  // 创建 Shadow Root
  const shadowRoot = shadowHost.attachShadow({ mode: 'open' });
  
  // 添加基础样式到 Shadow DOM
  const style = document.createElement('style');
  style.textContent = `
    :host {
      display: block;
      width: 100%;
      height: auto;
    }
    img {
      max-width: 100% !important;
      height: auto !important;
      display: block;
      margin: 0 auto;
    }
    iframe {
      width: 100% !important;
      border: none !important;
    }
    p {
      margin: 1em 0;
      line-height: 1.6;
    }
    * {
      box-sizing: border-box;
    }
  `;
  shadowRoot.appendChild(style);
  
  // 创建内容容器
  const contentDiv = document.createElement('div');
  contentDiv.innerHTML = currentArticle.value.content || '';
  shadowRoot.appendChild(contentDiv);
  
  // 将 Shadow Host 添加到容器中
  shadowContainer.value.appendChild(shadowHost);
};

// 切换文章阅读状态
const toggleReadStatus = async (record: any) => {
  try {
    const newReadStatus = record.is_read === 1 ? false : true;
    await toggleArticleReadStatus(record.id, newReadStatus);
    
    // 更新本地数据
    const index = articles.value.findIndex(item => item.id === record.id);
    if (index !== -1) {
      articles.value[index].is_read = newReadStatus ? 1 : 0;
    }
    
    Message.success(`文章已标记为${newReadStatus ? '已读' : '未读'}`);
  } catch (error) {
    console.error('更新阅读状态失败:', error);
    Message.error('更新阅读状态失败');
  }
};

const toggleFavoriteStatus = async (record: any) => {
  try {
    const newFavoriteStatus = record.is_favorite === 1 ? false : true
    await toggleArticleFavoriteStatus(record.id, newFavoriteStatus)

    const index = articles.value.findIndex(item => item.id === record.id)
    if (index !== -1) {
      articles.value[index].is_favorite = newFavoriteStatus ? 1 : 0
    }

    Message.success(newFavoriteStatus ? '收藏成功' : '已取消收藏')

    if (onlyFavorite.value && !newFavoriteStatus) {
      pagination.value.current = 1
      fetchArticles()
    }
  } catch (error) {
    console.error('更新收藏状态失败:', error)
    Message.error('更新收藏状态失败')
  }
}
</script>

<style scoped>
.article-list {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.article-list :deep(.arco-layout) {
  display: flex;
  width: 100%;
  height: 100%;
}

.article-list :deep(.arco-layout-sider) {
  flex-shrink: 0;
  overflow: hidden;
}

.article-list :deep(.arco-layout-content) {
  flex: 1;
  min-width: 0;
  overflow: auto;
  box-sizing: border-box;
}

/* ========== 统一的左侧列表样式 ========== */

/* 所有列表项的共同样式 */
.list-item {
  padding: 8px 12px;
  margin: 2px 8px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: all 0.2s ease;
  user-select: none;
}

/* 悬浮效果 */
.list-item:hover {
  background-color: var(--color-fill-2);
}

/* 选中状态（激活的项） */
.list-item.active {
  background-color: var(--color-primary-light-1);
  color: var(--color-primary-6);
}

/* 文件夹项的箭头区域 */
.folder-arrow {
  width: 20px;
  display: inline-flex;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}
/* 文件夹编辑输入框 */
.folder-edit-input {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--color-primary-6);
  border-radius: 4px;
  outline: none;
  font-size: 14px;
  background: var(--color-bg-2);
  color: var(--color-text-1);
}
/* 文件夹内的公众号子项（缩进显示） */
.folder-children {
  margin-left: 28px;
}

/* 文件夹内的公众号子项样式 */
.folder-children .list-item {
  padding-left: 12px;
}

/* 拖拽时的视觉反馈 */
.list-item.dragging {
  opacity: 0.5;
}

/* 拖拽目标高亮 */
.folder-item.drag-over {
  background-color: var(--color-primary-light-2);
  border: 1px dashed var(--color-primary-6);
}

/* 分组区域 */
.section-title {
  padding: 12px 12px 6px 12px;
  font-size: 12px;
  color: var(--color-text-3);
  font-weight: 500;
  letter-spacing: 0.5px;
}

.section-divider {
  height: 1px;
  background: var(--color-fill-3);
  margin: 8px 12px;
}

.avatar-small {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}

.item-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-text-3);
  flex-shrink: 0;
}

.active .item-count {
  color: var(--color-primary-6);
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.search-input {
  flex: 1;
  min-width: 0;
  max-width: calc(100% - 140px);
}

.favorite-filter {
  flex: 0 0 auto;
  white-space: nowrap;
}

.featured-url-example {
  margin-top: 8px;
  color: var(--color-text-3);
  font-size: 12px;
}

.featured-url-input-wrapper {
  width: 100%;
}

:deep(.arco-table-th-item) {
  justify-content: center;
}

:deep(.arco-table) {
  width: 100% !important;
}

:deep(.arco-table-container) {
  width: 100% !important;
  overflow-x: auto;
}

:deep(.arco-table-content) {
  overflow-x: auto;
}

:deep(.arco-table-element) {
  width: 100% !important;
  table-layout: auto !important;
}

:deep(.arco-card) {
  width: 100%;
  box-sizing: border-box;
}

:deep(.arco-card-body) {
  width: 100%;
  overflow: hidden;
}

.arco-drawer-body img {
  max-width: 100vw !important;
  margin: 0 auto !important;
  padding: 0 !important;
}

.arco-drawer-body {
  z-index: 9999 !important;
}

:deep(.arco-btn .arco-icon-down) {
  transition: transform 0.2s ease-in-out;
}

:deep(.arco-dropdown-open .arco-icon-down) {
  transform: rotate(180deg);
}

:deep(.image-preview-tooltip) {
  padding: 4px !important;
  background: transparent !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
}

:deep(.arco-tooltip-content) {
  background: transparent !important;
}
.empty-drop-tip {
  padding: 16px 12px;
  text-align: center;
  color: var(--color-text-3);
  font-size: 12px;
  border: 1px dashed var(--color-fill-3);
  border-radius: 8px;
  margin: 8px;
  background-color: var(--color-fill-1);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.empty-drop-tip:hover {
  border-color: var(--color-primary-6);
  background-color: var(--color-primary-light-1);
}
</style>

<style>
#article-model img {
  max-width: 100% !important;
  border-width: 0px !important;
}
iframe {
  width: 100% !important;
  border: 0 !important;
}
</style>
