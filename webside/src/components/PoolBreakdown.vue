<template>
  <!-- 「这笔钱是从哪几批注资里出的、各按什么汇率折的」。显卡和整机同一个形状的数据，
       所以同一个组件，别在两个详情页里各画一遍。 -->
  <el-card shadow="never" class="pool-card">
    <template #header>
      <div class="pool-head">
        <span>{{ t('funds.poolBreakdown') }}</span>
        <router-link to="/funds" class="link">{{ t('route.funds') }} ↗</router-link>
      </div>
    </template>
    <div v-for="d in draws" :key="d.id" class="pool-draw">
      <div class="pool-draw-head">
        <span>{{ t('funds.cat.' + d.category) }}</span>
        <b class="pcr-mono">{{ jpy(d.amount) }} → {{ cny(d.cny_amount) }}</b>
      </div>
      <div v-for="(a, i) in d.allocations" :key="i" class="pool-alloc">
        <span class="pcr-dim pcr-mono">{{ a.inject_date }}</span>
        <span class="pcr-mono">{{ jpy(a.amount) }}</span>
        <span class="pcr-dim">× {{ formatRate(a.fx_rate) }}/{{ RATE_UNIT }} =</span>
        <span class="pcr-mono">{{ cny(a.cny_amount) }}</span>
      </div>
      <div v-if="d.shortfall" class="pool-alloc short">
        <span>{{ t('funds.shortfall') }}</span>
        <span class="pcr-mono">{{ jpy(d.shortfall) }}</span>
        <span class="pcr-dim">{{ t('funds.shortfallHint') }}</span>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { RATE_UNIT, cny, formatMoney, formatRate } from '@/utils/format'

defineProps({ draws: { type: Array, default: () => [] } })
const { t } = useI18n()
const jpy = (v) => formatMoney(v, 'JPY')
</script>

<style scoped>
.pool-head { display: flex; align-items: center; justify-content: space-between; }
.pool-draw { padding: 6px 0; border-bottom: 1px solid #1c2740; }
.pool-draw:last-child { border-bottom: none; }
.pool-draw-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: #c7d0de; margin-bottom: 4px; }
.pool-alloc { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #9aa6b8; padding: 2px 0 2px 10px; }
.pool-alloc.short { color: #e6a23c; }
.link { color: #8fb8ff; text-decoration: none; font-size: 12px; }
.link:hover { text-decoration: underline; }
</style>
