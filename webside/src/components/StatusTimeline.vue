<template>
  <!-- 状态流转：这张卡 / 这台机器什么时候到的哪一步。显卡与整机各有一张日志表，
       但形状一样（见 devices.log_status），展示就共用这一份。
       圆点用状态色（format.js 那一份）：一条时间轴上颜色和列表里的标签对得上，
       才能一眼看出这台机器是卡在「测试不通过」还是正常走到了「已打款」。 -->
  <el-card shadow="never" class="log-card">
    <template #header>{{ t('card.status') }}</template>
    <el-timeline>
      <el-timeline-item
        v-for="(log, i) in logs"
        :key="i"
        :timestamp="fmtTime(log.occurred_at)"
        :color="statusColor(log.to_status)"
        placement="top"
      >
        {{ t('status.' + log.to_status) }}
        <span v-if="log.note" class="pcr-dim">· {{ log.note }}</span>
      </el-timeline-item>
    </el-timeline>
  </el-card>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { statusColor } from '@/utils/format'

defineProps({ logs: { type: Array, default: () => [] } })
const { t } = useI18n()

function fmtTime(iso) {
  return iso ? iso.replace('T', ' ').slice(0, 16) : ''
}
</script>
