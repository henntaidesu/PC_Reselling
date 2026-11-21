<template>
  <!-- 「这笔钱是从哪几批注资里出的、各按什么汇率折的」，以及以日元卖掉时那笔钱回到了谁的池里。
       显卡和整机同一个形状的数据，所以同一个组件，别在两个详情页里各画一遍。 -->
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
        <!-- 这一段吃的是谁的钱。池子是几个人凑的时候，「这张卡花了谁的钱」就在这一行上 -->
        <el-tag v-if="a.contributor" size="small" type="primary" effect="plain">{{ a.contributor }}</el-tag>
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
    <!-- 出售回流：日元售价按出售日汇率进了归属人的池（整机一个部件一笔）。它是一批注资，
         所以给的是「进了多少、按什么价、已经被后面的货用掉多少」 -->
    <div v-for="r in returns" :key="'r' + r.id" class="pool-draw">
      <div class="pool-draw-head">
        <span>
          {{ t('funds.typeSale') }}
          <template v-if="r.sale_source?.part_type">
            · {{ t('partType.' + r.sale_source.part_type) }}{{ r.sale_source.name ? ' ' + r.sale_source.name : '' }}
          </template>
        </span>
        <b class="pcr-mono">{{ jpy(r.amount) }} → {{ cny(r.cny_cost) }}</b>
      </div>
      <div class="pool-alloc">
        <span class="pcr-dim pcr-mono">{{ r.inject_date }}</span>
        <el-tag v-if="r.contributor" size="small" type="primary" effect="plain">{{ r.contributor }}</el-tag>
        <span class="pcr-mono">{{ jpy(r.amount) }}</span>
        <span class="pcr-dim">× {{ r.fx_rate ? formatRate(r.fx_rate) : '—' }}/{{ RATE_UNIT }} =</span>
        <span class="pcr-mono">{{ cny(r.cny_cost) }}</span>
      </div>
      <div v-if="r.used_amount" class="pool-alloc pcr-dim">
        <span>{{ t('funds.used') }} <span class="pcr-mono">{{ jpy(r.used_amount) }}</span></span>
        <span>{{ t('funds.remaining') }} <span class="pcr-mono">{{ jpy(r.remaining_amount) }}</span></span>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { RATE_UNIT, cny, formatMoney, formatRate } from '@/utils/format'

defineProps({
  draws: { type: Array, default: () => [] },
  // 出售回流（详情响应的 fund_returns），与资金池页的注资行同一个形状
  returns: { type: Array, default: () => [] }
})
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

@media (max-width: 768px) {
  /* 「日期 · 日元 · × 汇率 = · 人民币」四段排一行，窄屏上只要金额上了六位就会顶出去。
     让它折行而不是压扁——这一行是「这笔钱按什么汇率折的」的完整算式，缺一段就对不上账。
     资金池页面那份明细（Funds 的 .alloc-line）是同样的处理。 */
  .pool-alloc { flex-wrap: wrap; gap: 4px 8px; }
}
</style>
