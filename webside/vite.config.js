import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 前端 dev server 端口。后端在 9910（见 conf.ini），两者错开，
// 同机跑 FreeMarket_Manager（9600/9601）和图床（9990）时也不打架。
const DEV_PORT = Number(process.env.PCR_DEV_PORT) || 9911
const BACKEND = process.env.PCR_DEV_BACKEND || 'http://127.0.0.1:9910'

// 外网访问下的热重载。页面能打开不代表 HMR 能连上：那条 WebSocket 的地址是浏览器
// 侧算出来的，默认取「页面的 host + dev server 的端口 + 页面的 http/https」——公网 IP
// 直连 9911 时这套默认值正好对，但只要中间隔了一层（路由器把外部端口映射成别的号、
// 反代成 https、内网穿透给了另一个域名），浏览器就会去连一个不存在的地址：页面一切
// 正常，只是改代码不刷新、控制台一直刷连接失败——看不出和「外网」有什么关系。
//
// 所以做成环境变量按入口临时指定，不写死：域名会变、端口映射各人不同，写进文件只会
// 变成下一个人要改回来的东西。
//   PCR_HMR_HOST      浏览器该连的主机名（反代 / 穿透时填对外域名）
//   PCR_HMR_PORT      浏览器该连的端口（https 反代填 443，端口映射填映射后的号）
//   PCR_HMR_PROTOCOL  ws 或 wss（对外是 https 就必须 wss，否则浏览器直接拒绝混合内容）
const hmr = {
  host: process.env.PCR_HMR_HOST || undefined,
  clientPort: Number(process.env.PCR_HMR_PORT) || undefined,
  protocol: process.env.PCR_HMR_PROTOCOL || undefined
}
// 一个都没给就别把 hmr 传下去——传一个全是 undefined 的对象和不传不等价，
// Vite 会当作「已显式配置」，反而绕开它自己那套按页面地址推断的默认行为。
const hmrConfigured = Object.values(hmr).some((v) => v !== undefined)

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    // 按 Safari 15 压 CSS：默认 target 会把 `@media (max-width: 768px)` 压成
    // 范围语法，iOS 16.4 以下整段忽略、手机样式全失效。
    cssTarget: 'safari15'
  },
  server: {
    // 0.0.0.0：本机之外（内网手机、公网映射进来的客户端）也能访问。
    // 注意这只决定「监听在哪」——Windows 防火墙默认仍会把外来连接静默丢掉，
    // 表现成连接超时而控制台一行日志都没有。用 open_firewall.bat 放行一次。
    host: '0.0.0.0',
    port: DEV_PORT,
    strictPort: true,
    // 放行全部 Host：内网直连 IP、公网域名、穿透分配的随机域名都不用改配置。
    // Vite 6 默认按 Host 头拦陌生域名（防 DNS 重绑定），不放开的话外网访问只会
    // 看到一句 "Blocked request. This host is not allowed."，很容易误判成没连上。
    allowedHosts: true,
    // dev server 自己的跨域响应头。Vite 6 默认只认 localhost 来源，外网调试时
    // （另一个页面 fetch 这里的资源）会被挡下；这是自用的开发机，索性放开。
    cors: true,
    // 只在显式给了 PCR_HMR_* 时才覆盖，其余情况交回 Vite 的默认推断
    ...(hmrConfigured ? { hmr } : {}),
    proxy: {
      // 后端全部端点都在 /api 下，一条代理规则就够。走服务端转发而不是让浏览器
      // 直连 9910：外网只放行一个端口时前端照样能用，也不牵扯跨域。
      '/api': { target: BACKEND, changeOrigin: true }
    }
  }
})
