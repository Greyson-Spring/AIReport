// web_ui/src/api/folder.ts
import http from './http';

// 文件夹类型定义
export interface Folder {
  id: number;
  user_id: string;
  name: string;
  created_at: string;
  feed_count?: number;
}

// 创建文件夹
export const createFolder = (name: string) => {
  return http.post('/wx/folder/create', { name });
};

// 获取文件夹列表
export const getFolderList = () => {
  return http.get('/wx/folder/list');
};

// 获取文件夹详情（包含里面的公众号）
export const getFolderDetail = (folderId: number) => {
  return http.get(`/wx/folder/${folderId}`);
};

// 更新文件夹名称
export const updateFolder = (folderId: number, name: string) => {
  return http.put(`/wx/folder/${folderId}`, { name });
};

// 删除文件夹
export const deleteFolder = (folderId: number) => {
  return http.delete(`/wx/folder/${folderId}`);
};

// 批量添加公众号到文件夹
export const addFeedsToFolder = (folderId: number, feedIds: string[]) => {
  return http.post(`/wx/folder/${folderId}/feeds`, { feed_ids: feedIds });
};

// 从文件夹移除单个公众号
export const removeFeedFromFolder = (folderId: number, feedId: string) => {
  return http.delete(`/wx/folder/${folderId}/feeds/${feedId}`);
};

// 获取文件夹内的公众号列表
export const getFolderFeeds = (folderId: number, page?: number, size?: number) => {
  return http.get(`/wx/folder/${folderId}/feeds`, { params: { page, size } });
};
