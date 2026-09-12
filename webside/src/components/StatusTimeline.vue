<template>
  <!-- 状态流转：这张卡 / 这台机器什么时候到的哪一步。显卡与整机各有一张日志表，
       但形状一样（见 devices.log_status），展示就共用这一份。 -->
  <el-card shadow="never" class="log-card">
    <template #header>{{ t('card.status') }}</template>
    <el-timeline>
      <el-timeline-item
        v-for="(log, i) in logs"
        :key="i"
        :timestamp="fmtTime(log.occurred_at)"
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

defineProps({ logs: { type: Array, default: () => [] } })
const { t } = useI18n()

function fmtTime(iso) {
  return iso ? iso.replace('T', ' ').slice(0, 16) : ''
}
</script>
