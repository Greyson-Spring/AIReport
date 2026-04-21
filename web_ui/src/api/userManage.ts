import http from './http'

export interface UserItem {
  username: string
  nickname: string
  email: string
  avatar: string
  role: string
  is_active: boolean
  menu_permissions: string[]
  created_at: string
  updated_at: string
}

export interface UserListResult {
  total: number
  page: number
  page_size: number
  list: UserItem[]
}

export interface CreateUserParams {
  username: string
  password: string
  email: string
  role?: string
  is_active?: boolean
  menu_permissions?: string[]
}

export interface UpdateUserParams {
  username: string
  email?: string
  role?: string
  is_active?: boolean
  menu_permissions?: string[]
}

export const getUserList = (page = 1, pageSize = 50) => {
  return http.get<{ code: number; data: UserListResult }>(`/wx/user/list?page=${page}&page_size=${pageSize}`)
}

export const createUser = (data: CreateUserParams) => {
  return http.post('/wx/user', data)
}

export const updateUser = (data: UpdateUserParams) => {
  return http.put('/wx/user', data)
}

export const deleteUser = (username: string) => {
  return http.delete(`/wx/user/${username}`)
}

export const resetUserPassword = (username: string, newPassword: string) => {
  return http.put(`/wx/user/${username}/reset-password`, { new_password: newPassword })
}
