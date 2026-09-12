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

// 图标整包注册。看着像浪费，实测不是：Rollup 会把没用到的摇掉，改成手写清单只注册
// 53 个，产物大小分毫不差（连一个都不注册也一样）。而模板里既有 `<Odometer />` 也有
// `:is="'Odometer'"` 这种按字符串取的写法，后者只能靠全局注册——为零收益换一条
// 「加图标要记得登记、忘了就静默消失」的规矩不划算。
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(ElementPlus, { locale: elementLocales[currentLocale.value] || elementLocales['zh-CN'] })
app.mount('#app')
