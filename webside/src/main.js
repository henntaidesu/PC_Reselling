import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import i18n, { elementLocales, currentLocale } from './i18n'

// 全站强制暗色主题，与 FreeMarket_Manager 一致
document.documentElement.classList.add('dark')

// 拖图上传时手一抖没落在投放区里，浏览器默认行为是直接打开那个文件——整页被顶掉，
// 详情页里还没防抖存下去的改动就跟着没了。所以在 window 上兜住所有落空的拖放。
// 冒泡到这里时投放区早已把文件收走了，这里再 preventDefault 一次不影响它。
window.addEventListener('dragover', (e) => e.preventDefault())
window.addEventListener('drop', (e) => e.preventDefault())

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(ElementPlus, { locale: elementLocales[currentLocale.value] || elementLocales['zh-CN'] })
app.mount('#app')
