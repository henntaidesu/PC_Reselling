import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login/index.vue'),
    meta: { public: true, titleKey: 'route.login' }
  },
  {
    path: '/',
    component: () => import('@/components/Layout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard/index.vue'), meta: { titleKey: 'route.dashboard', icon: 'Odometer' } },
      { path: 'cards', name: 'Cards', component: () => import('@/views/Cards/index.vue'), meta: { titleKey: 'route.cards', icon: 'Cpu' } },
      // 详情不再是独立页面，而是库存列表上的悬浮弹窗（?open=card-12 / device-5）。
      // 老地址保留成重定向：收藏夹、聊天记录里贴过的链接照样能打开那一件
      { path: 'cards/:id', redirect: (to) => ({ path: '/cards', query: { open: `card-${to.params.id}` } }) },
      { path: 'devices/:id', redirect: (to) => ({ path: '/cards', query: { ...to.query, open: `device-${to.params.id}` } }) },
      { path: 'funds', name: 'Funds', component: () => import('@/views/Funds/index.vue'), meta: { titleKey: 'route.funds', icon: 'Wallet' } },
      { path: 'fx', name: 'Fx', component: () => import('@/views/Fx/index.vue'), meta: { titleKey: 'route.fx', icon: 'TrendCharts' } },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings/index.vue'), meta: { titleKey: 'route.settings', icon: 'Setting' } }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const isPublic = Boolean(to.meta?.public)
  const token = localStorage.getItem('auth_token')
  if (!isPublic && !token) return next('/login')
  // 从门户跳回来带着一次性票时，哪怕本机已经登着（别的账号）也要让登录页把票换掉——
  // 否则票被这里吞了，点门户卡片永远进的是上一个人的账号
  const ssoReturn = to.path === '/login' && (to.query.sso_ticket || to.query.sso_error)
  if (to.path === '/login' && token && !ssoReturn) return next('/dashboard')
  next()
})

export default router
