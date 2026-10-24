import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(safeParse(localStorage.getItem('auth_user')))
  const isAdmin = computed(() => Boolean(user.value?.is_admin))
  const displayName = computed(() => user.value?.display_name || user.value?.username || '')

  function safeParse(raw) {
    try {
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  function setUser(u) {
    localStorage.setItem('auth_user', JSON.stringify(u))
    user.value = u
  }

  // 账号密码登录与门户单点登录的唯一入口：后端两条路回的都是 { token, user }（auth.issue_login）
  function enter(res) {
    localStorage.setItem('auth_token', res.token)
    setUser(res.user)
    return res.user
  }

  async function login(username, password) {
    return enter(await authApi.login({ username, password }))
  }

  // localStorage 里那份是登录那一刻的快照，令牌又永不过期：管理员后来改了他的名字、
  // 提降了管理员，不重新问一次的话界面会一直停在老样子。进主框架时调一次
  async function refresh() {
    try {
      setUser(await authApi.me())
    } catch { /* 401 由 http.js 统一处理 */ }
  }

  function logout() {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    user.value = null
    window.location.hash = '#/login'
  }

  return { user, isAdmin, displayName, enter, login, refresh, setUser, logout }
})
