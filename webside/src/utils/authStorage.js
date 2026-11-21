// 登录态（令牌 + 当前用户快照）在 localStorage 里的唯一存取点，http.js / 路由守卫 / auth store 都走这里。
//
// 键名不能用 auth_token 这种通用名：PCR 常经门户「整站」代理打开（https://门户/api/proxy/<卡片 id>/...），
// 同一门户下所有被代理的系统同源，共用一份 localStorage。FreeMarket_Manager 也用 auth_token，
// 它的页面每 30 秒轮询一次，拿着 PCR 写进去的令牌问自己的后端，401 后把这个键清掉、或重新登录
// 写成它自己的令牌——PCR 下一个请求就被踢回登录页。表现是「登进去一两分钟就说令牌无效」，
// 单独开哪一个都复现不了。反过来 PCR 收到 401 时清键，也会把它踢下线。
//
// 除了 pcr_ 前缀再按站点根路径分一层：同一门户上两张卡片指向两个 PCR 实例时，光有前缀照样互相顶掉。
// 哈希路由下 pathname 就是站点根（直连是 /，经代理是 /api/proxy/<id>/__portal__/http/主机/），
// 去掉最后一段是让 /index.html 这种入口也落在同一个键上。
const SCOPE = window.location.pathname.replace(/[^/]*$/, '')
const TOKEN_KEY = `pcr_auth_token:${SCOPE}`
const USER_KEY = `pcr_auth_user:${SCOPE}`

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
