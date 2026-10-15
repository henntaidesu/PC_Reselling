<template>
  <!-- 置换记录：这一行现在指的那张卡，未必是当初买回来的那张。每条记录列出置换前两头
       各是什么（后端快照，字段名统一用显卡那一侧的），互换之后行上的值已经是对方的了。 -->
  <el-card shadow="never" class="swap-card">
    <template #header>{{ t('swap.history') }}</template>
    <div v-for="s in swaps" :key="s.id" class="sh-item">
      <div class="sh-head">
        <span class="pcr-mono pcr-dim">{{ s.swap_date }}</span>
        <span class="pcr-mono">{{ s.card_mgmt_no || t('swap.deleted') }}</span>
        <span class="sh-arrow">⇄</span>
        <span class="pcr-mono">{{ s.device_mgmt_no || t('swap.deleted') }}</span>
        <span v-if="s.device_title" class="pcr-dim">{{ s.device_title }}</span>
      </div>
      <div class="sh-line"><span class="sh-k">{{ t('swap.cardBefore') }}</span>{{ describe(s.card_before) }}</div>
      <div class="sh-line"><span class="sh-k">{{ t('swap.partBefore') }}</span>{{ describe(s.part_before) }}</div>
      <div v-if="s.note" class="sh-line pcr-dim">{{ s.note }}</div>
    </div>
  </el-card>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({ swaps: { type: Array, default: () => [] } })
const { t } = useI18n()

function describe(x) {
  if (!x) return '—'
  const name = [x.brand, x.model].filter(Boolean).join(' ') || '—'
  const parts = [
    name,
    x.core_no && `${t('card.coreNo')} ${x.core_no}`,
    x.serial_no && `SN ${x.serial_no}`,
    x.media_count ? t('swap.mediaCount', { n: x.media_count }) : null
  ]
  return parts.filter(Boolean).join(' · ') + (x.owner ? `（${x.owner}）` : '')
}
</script>

<style scoped>
.swap-card { margin-bottom: 12px; }
.sh-item { padding: 8px 0; border-bottom: 1px dashed var(--pcr-border); font-size: 13px; }
.sh-item:last-child { border-bottom: none; }
.sh-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; margin-bottom: 4px; }
.sh-arrow { color: #8fb8ff; }
.sh-line { line-height: 1.7; color: #d6deea; word-break: break-all; }
.sh-k { color: #8a94a6; font-size: 12px; margin-right: 6px; }
</style>
