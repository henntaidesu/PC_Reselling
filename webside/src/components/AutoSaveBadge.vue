<template>
  <!-- 详情页没有保存按钮，这里是「东西存进去了没有」的唯一反馈。存过一次之后就一直
       挂着「已自动保存」，不只在保存的那一瞬间闪一下；但一个字都还没改时不出声——
       页面一打开就贴一条「改动即时保存」，说的是一件还没发生的事。 -->
  <span class="autosave" :class="{ active: saving }">
    <template v-if="saving"><el-icon class="spin"><Loading /></el-icon>{{ t('card.saving') }}</template>
    <template v-else-if="savedOnce"><el-icon><Select /></el-icon>{{ t('card.autoSaved') }}</template>
  </span>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { Loading, Select } from '@element-plus/icons-vue'

defineProps({
  saving: { type: Boolean, default: false },
  savedOnce: { type: Boolean, default: false }
})
const { t } = useI18n()
</script>

<style scoped>
.autosave { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: #6f7b8e; }
.autosave.active { color: #8fb8ff; }
.autosave .spin { animation: pcr-spin 0.9s linear infinite; }
@keyframes pcr-spin { to { transform: rotate(360deg); } }
</style>
