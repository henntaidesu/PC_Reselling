<template>
  <div ref="el" class="echart" :style="{ height }"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
// 按需引入。`import * as echarts from 'echarts'` 会把三十几种图表、地图、SVG 渲染器
// 全打进包里——1.0MB（gzip 344KB），而概览页恰恰是首页，手机冷启动一进来就得下这一份。
// 全站只用到折线和柱状两种图（含堆叠柱做的占比条），组件只用到直角坐标系、提示框和图例。
//
// 加新图表类型时要**同时**在这里注册对应的 XxxChart / XxxComponent，否则那张图不报错、
// 就是画不出来（控制台只有一句 echarts 的注册提示，很容易看漏）。
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '320px' }
})

const el = ref()
let chart = null

function render() {
  if (!chart) return
  // notMerge:true —— 系列数量变化时（比如筛选后月份变少）不留下上一次的残影
  chart.setOption(props.option, true)
}

// resize 防抖。手机上这不是「偶尔缩放窗口」那种事件：iOS Safari 滚动时地址栏
// 收起 / 展开就会连着抛一串 resize，概览页同屏有五个图表实例，每一下都重排一次
// 的话，滚动会明显发涩。150ms 足够盖住地址栏那一次动画，人也感觉不到延迟。
let resizeTimer = null
function resize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    resizeTimer = null
    chart?.resize()
  }, 150)
}

onMounted(() => {
  // 不挂 echarts 自带的 'dark' 主题：那个主题文件是 UMD 的，import 进来会 require
  // 整个 echarts，按需引入就白做了。配色改由每张图自己从 utils/chartTheme.js 取，
  // 那边本来也已经把颜色一个个显式写死了（概览页从一开始就是这样，汇率页是随这次改的）。
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', resize)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  // 定时器必须清掉：不清的话它会在组件卸载之后才跑，那时 chart 已经 dispose，
  // 虽然有 ?. 兜着不报错，但闭包连同那个已销毁的实例一起被多留 150ms
  if (resizeTimer) clearTimeout(resizeTimer)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.echart { width: 100%; }
/* echarts 的 dark 主题底色是纯黑，盖成卡片色 */
.echart :deep(canvas) { background: transparent !important; }
</style>
