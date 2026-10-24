import http from './http'

export const authApi = {
  login: (payload) => http.post('/auth/login', payload),
  me: () => http.get('/auth/me'),
  // 只能改自己的显示名；用户名是登录名，归管理员在用户管理里改
  updateProfile: (payload) => http.put('/auth/profile', payload),
  changePassword: (payload) => http.post('/auth/change-password', payload)
}

// 用户管理（仅管理员）。重置密码 / 停用 / 强制下线都会让那个人已有的登录全部失效
export const usersApi = {
  list: () => http.get('/users'),
  // password 不给 = 没有本地密码，只能从门户单点登录进来
  create: (payload) => http.post('/users', payload),
  update: (id, payload) => http.put(`/users/${id}`, payload),
  resetPassword: (id, password) => http.post(`/users/${id}/password`, { password }),
  revoke: (id) => http.post(`/users/${id}/revoke`),
  remove: (id) => http.delete(`/users/${id}`)
}

// 门户单点登录（门户当 OIDC 提供方，本系统当客户端），流程见后端 src/portal_sso/flow.py
export const ssoApi = {
  // 本系统开没开单点登录、按钮文案（没开时登录页不画按钮）
  status: () => http.get('/sso/status'),
  // 拿门户跳回来时带的一次性票换 JWT，返回形状与账号密码登录相同 { token, user }
  exchange: (ticket) => http.post('/sso/exchange', { ticket }),
  // 整页跳转去门户授权（不是 fetch：授权要浏览器自己走完门户那一趟）。
  // **相对当前页面拼**而不是写成 /api/...：经门户代理打开时页面在 /api/proxy/<id>/ 底下，
  // 根绝对地址会打到门户自己身上。后端那个跳板页再从它自己的地址里算出 base
  loginUrl: () => new URL('api/v1/sso/login', location.origin + location.pathname).href,

  getConfig: () => http.get('/sso/config'),
  // client_secret 留空 = 不修改
  saveConfig: (payload) => http.put('/sso/config', payload),
  // 用已保存的配置读门户的发现文档，核对地址
  test: () => http.post('/sso/test'),
  bindings: () => http.get('/sso/bindings'),
  unbind: (id) => http.delete(`/sso/bindings/${id}`)
}

export const cardsApi = {
  list: (params) => http.get('/cards', { params }),
  // 顶部统计：对当前筛选下的全部卡做汇总（同一套筛选参数）
  stats: (params) => http.get('/cards/stats', { params }),
  get: (id) => http.get(`/cards/${id}`),
  create: (payload) => http.post('/cards', payload),
  // 点「新增」即建的空草稿卡，只为拿到 id 好跳进详情页（图片也就能立刻传）
  createDraft: () => http.post('/cards/draft'),
  update: (id, payload) => http.put(`/cards/${id}`, payload),
  changeStatus: (id, payload) => http.patch(`/cards/${id}/status`, payload),
  refreshFx: (id) => http.post(`/cards/${id}/refresh-fx`),
  remove: (id, purgeMedia = false) => http.delete(`/cards/${id}`, { params: { purge_media: purgeMedia } }),
  nextMgmtNo: () => http.get('/cards/next-mgmt-no')
}

// 库存合并列表：显卡与整机在同一张表里，行上带 kind 区分。筛选、排序、分页
// 都在后端统一做，前端不必自己把两个列表拼起来。
export const inventoryApi = {
  list: (params) => http.get('/inventory', { params }),
  stats: (params) => http.get('/inventory/stats', { params }),
  // 筛选下拉的联动选项，参数与 list 相同
  facets: (params) => http.get('/inventory/facets', { params })
}

// 整机设备的增删改查：一次购入（一个总价）拆成多个部件分别出售。部件随设备整体提交，
// 后端按 id 增量写回 device_parts（见 devices_api._write_parts）。列表走上面的 inventoryApi。
export const devicesApi = {
  get: (id) => http.get(`/devices/${id}`),
  create: (payload) => http.post('/devices', payload),
  // 点「新增」即建的空草稿设备，只为拿到 id 与管理编号，随即跳进它的详情页
  createDraft: () => http.post('/devices/draft'),
  update: (id, payload) => http.put(`/devices/${id}`, payload),
  changeStatus: (id, payload) => http.patch(`/devices/${id}/status`, payload),
  refreshFx: (id) => http.post(`/devices/${id}/refresh-fx`),
  remove: (id) => http.delete(`/devices/${id}`),
  nextMgmtNo: () => http.get('/devices/next-mgmt-no')
}

export const mediaApi = {
  // 上传走 multipart，交给调用方自己构造 FormData
  upload: (formData) =>
    http.post('/media/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 600000 }),
  listForCard: (cardId) => http.get(`/media/card/${cardId}`),
  // 平铺一组图（不分类）。owner 只有两种：'parts' = 某个部件，'devices' = 整机本身。
  // 两边的请求与响应完全同形，所以只留这一组方法，别按归属各写一套。
  flatList: (owner, ownerId) => http.get(`/media/${owner}/${ownerId}`),
  flatUpload: (owner, ownerId, formData) =>
    http.post(`/media/${owner}/${ownerId}`, formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 600000 }),
  flatRemove: (owner, mediaId, purge = true) =>
    http.delete(`/media/${owner}/items/${mediaId}`, { params: { purge } }),
  // 平铺那组的重排。载荷和下面的 reorder 同形，但路径里要带归属 id：后端据此只动这一个
  // 部件 / 这一台整机名下的行，混进来的别人家的 id 会被忽略而不是把那边也排了。
  flatReorder: (owner, ownerId, mediaIds) =>
    http.put(`/media/${owner}/${ownerId}/reorder`, { media_ids: mediaIds }),
  // 显卡那份按分类各排各的，传的是某一个分类的完整顺序
  reorder: (mediaIds) => http.put('/media/reorder', { media_ids: mediaIds }),
  remove: (mediaId, purge = true) => http.delete(`/media/${mediaId}`, { params: { purge } })
}

export const fxApi = {
  rate: (params) => http.get('/fx/rate', { params }),
  history: (params) => http.get('/fx/history', { params }),
  refresh: (params) => http.post('/fx/refresh', null, { params }),
  getConfig: () => http.get('/fx/config'),
  setConfig: (params) => http.put('/fx/config', null, { params })
}

// 资金池：注资、扣款与 FIFO 分摊。写操作的响应里直接带回重算后的总账与两张明细表，
// 前端拿到就能整页刷新，不必再补一次 GET。
export const fundsApi = {
  overview: () => http.get('/funds'),
  summary: () => http.get('/funds/summary'),
  injections: () => http.get('/funds/injections'),
  createInjection: (payload) => http.post('/funds/injections', payload),
  updateInjection: (id, payload) => http.put(`/funds/injections/${id}`, payload),
  removeInjection: (id) => http.delete(`/funds/injections/${id}`),
  draws: (params) => http.get('/funds/draws', { params }),
  createDraw: (payload) => http.post('/funds/draws', payload),
  updateDraw: (id, payload) => http.put(`/funds/draws/${id}`, payload),
  removeDraw: (id) => http.delete(`/funds/draws/${id}`),
  rebuild: () => http.post('/funds/rebuild')
}

// 实物置换：单卡 ↔ 整机显卡部件（只换实物信息与图片，账目不动，见后端 src/swaps.py）。
// 记录本身跟着两头的详情响应走（swaps 字段），这里只有挑对象和执行两件事。
export const swapsApi = {
  // { card_id } 列出可换的整机显卡部件；{ part_id } 列出可换的单卡
  candidates: (params) => http.get('/swaps/candidates', { params }),
  create: (payload) => http.post('/swaps', payload)
}

export const optionsApi = {
  enums: () => http.get('/options/enums'),
  brands: () => http.get('/options/brands'),
  createBrand: (payload) => http.post('/options/brands', payload),
  removeBrand: (id) => http.delete(`/options/brands/${id}`),
  platforms: () => http.get('/options/platforms'),
  fundContributors: () => http.get('/options/fund-contributors'),
  createPlatform: (payload) => http.post('/options/platforms', payload),
  removePlatform: (id) => http.delete(`/options/platforms/${id}`),
  models: () => http.get('/options/models'),
  createModel: (payload) => http.post('/options/models', payload),
  removeModel: (id) => http.delete(`/options/models/${id}`),
  usedBrands: () => http.get('/options/used-brands')
}

export const dashboardApi = {
  summary: (params) => http.get('/dashboard/summary', { params }),
  recent: (params) => http.get('/dashboard/recent', { params }),
  topModels: (params) => http.get('/dashboard/top-models', { params })
}

export const systemApi = {
  getImageHosting: () => http.get('/system/image-hosting'),
  saveImageHosting: (payload) => http.put('/system/image-hosting', payload),
  testImageHosting: () => http.post('/system/image-hosting/test'),
  databaseStatus: () => http.get('/system/database'),
  databaseReconnect: () => http.post('/system/database/reconnect')
}
