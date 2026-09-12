<template>
  <el-tag size="small" effect="dark" :round="round" :style="tagStyle">{{ t('status.' + status) }}</el-tag>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { STATUS_OUTLINED, statusColor } from '@/utils/format'

// round=false 给下拉选项用：那里是一列等宽的块，圆角胶囊排在一起显得松散（见 StatusSelect.vue）
const props = defineProps({
  status: { type: String, required: true },
  round: { type: Boolean, default: true }
})
const { t } = useI18n()

// 颜色直接写成 el-tag 的三个 CSS 变量（行内样式盖得住组件自己那套 type 变量），
// 这样十个状态各有各的色，不用去凑 el-tag 只有五种的 type。
// 「意向购入」这类还没买下的画成描边：底透明、字与边框用状态色本身。
const tagStyle = computed(() => {
  const color = statusColor(props.status)
  const outlined = STATUS_OUTLINED.has(props.status)
  return {
    '--el-tag-bg-color': outlined ? 'transparent' : color,
    '--el-tag-border-color': color,
    '--el-tag-text-color': outlined ? color : '#fff'
  }
})
</script>
