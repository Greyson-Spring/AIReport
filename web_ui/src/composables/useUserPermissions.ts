import { ref } from 'vue'
import { getCurrentUser } from '@/api/auth'

const userRole = ref('')
const menuPermissions = ref<string[]>([])
const loaded = ref(false)

let loadPromise: Promise<void> | null = null

export function useUserPermissions() {
  const loadPermissions = async (force = false) => {
    if (loaded.value && !force) return
    if (loadPromise && !force) return loadPromise

    loadPromise = (async () => {
      try {
        const res: any = await getCurrentUser()
        userRole.value = res?.role || ''
        menuPermissions.value = res?.menu_permissions || []
      } catch {
        userRole.value = ''
        menuPermissions.value = []
      } finally {
        loaded.value = true
      }
    })()
    return loadPromise
  }

  const hasPermission = (key: string): boolean => {
    if (userRole.value === 'admin') return true
    return menuPermissions.value.includes(key)
  }

  return {
    userRole,
    menuPermissions,
    loaded,
    loadPermissions,
    hasPermission,
  }
}
