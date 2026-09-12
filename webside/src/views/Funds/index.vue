<template>
  <div class="funds-page" v-loading="loading">
    <div class="page-head">
      <h2 class="page-title">{{ t('route.funds') }}</h2>
      <div class="head-actions">
        <el-button :icon="Refresh" :loading="rebuilding" @click="rebuild">{{ t('funds.rebuild') }}</el-button>
        <el-button :icon="Minus" @click="openDraw()">{{ t('funds.addDraw') }}</el-button>
        <el-button type="primary" :icon="Plus" @click="openInjection()">{{ t('funds.addInjection') }}</el-button>
      </div>
    </div>

    <!-- 总账 -->
    <el-card class="stats-card" shadow="never">
      <el-row :gutter="16">
        <el-col v-for="card in statCards" :key="card.key" :xs="12" :sm="12" :md="8" :lg="6" :xl="4">
          <StatCard :label="card.label" :value="card.value" :icon="card.icon" :color="card.color" />
        </el-col>
      </el-row>
      <p class="pool-note pcr-dim">{{ t('funds.explainer') }}</p>
      <el-alert v-if="summary.shortfall" type="warning" :closable="false" show-icon class="mt"
        :title="t('funds.shortfallWarn', { amount: jpy(summary.shortfall) })" />
      <el-alert v-if="summary.incomplete" type="warning" :closable="false" show-icon class="mt"
        :title="t('funds.incompleteWarn')" />
    </el-card>

    <!-- 按出资人：池子里的钱是谁出的、被花掉多少、还剩多少。
         全部由注资与分摊反算，没有单独的「账户」——余额有第二个地方存着就一定会对不上。 -->
    <el-card v-if="contributors.length" class="table-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>{{ t('funds.contributors') }}</span>
          <span class="pcr-dim count">
            {{ t('funds.contributorHint') }}
            <el-button v-if="contributorFilter !== null" link type="primary" @click="contributorFilter = null">
              {{ t('funds.clearFilter') }}
            </el-button>
          </span>
        </div>
      </template>
      <el-table :data="contributors" class="pcr-table contrib-table" size="small" empty-text=" "
        :row-class-name="contributorRowClass" @row-click="toggleContributorFilter">
        <el-table-column :label="t('funds.contributor')" min-width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.name ? 'primary' : 'info'" effect="plain">
              {{ row.name || t('funds.noContributor') }}
            </el-tag>
            <span v-if="row.incomplete" class="pcr-dim sub"> · {{ t('funds.rateMissingTag') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('funds.injected')" align="right" min-width="120">
          <template #default="{ row }">
            <div class="pcr-mono">{{ jpy(row.injected) }}</div>
            <div class="pcr-dim sub pcr-mono">{{ cny(row.injected_cny) }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="t('funds.used')" align="right" min-width="110">
          <template #default="{ row }"><span class="pcr-mono">{{ jpy(row.used) }}</span></template>
        </el-table-column>
        <el-table-column :label="t('funds.remaining')" align="right" min-width="110">
          <template #default="{ row }"><span class="pcr-mono">{{ jpy(row.remaining) }}</span></template>
        </el-table-column>
        <!-- 分红与在库本金分两列，不合成一个数：一台刚买回来还没拆卖的整机，合起来看
             就是「亏了一整台的钱」，而它只是还没卖 -->
        <el-table-column :label="t('funds.dividend')" align="right" min-width="110">
          <template #default="{ row }">
            <span class="pcr-mono" :class="profitClass(row.dividend_cny)">{{ cny(row.dividend_cny) }}</span>
            <span v-if="row.pnl_incomplete" class="pcr-dim sub"> *</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('funds.stockCost')" align="right" min-width="110">
          <template #default="{ row }"><span class="pcr-mono">{{ cny(row.stock_cost_cny) }}</span></template>
        </el-table-column>
        <el-table-column :label="t('funds.share')" align="right" width="92">
          <template #default="{ row }">
            <span class="pcr-mono">{{ percent(row.share) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('funds.avgRate')" align="right" width="96">
          <template #default="{ row }">
            <span class="pcr-mono">{{ row.avg_rate ? formatRate(row.avg_rate) : '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="16">
      <!-- 注资批次 -->
      <el-col :xs="24" :lg="12">
        <el-card class="table-card" shadow="never">
          <template #header>
            <div class="card-head">
              <span>{{ t('funds.injections') }}</span>
              <span class="pcr-dim count">{{ t('common.total', { n: shownInjections.length }) }}</span>
            </div>
          </template>
          <el-table :data="shownInjections" class="pcr-table" size="small" empty-text=" ">
            <el-table-column :label="t('funds.injectDate')" width="104">
              <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.inject_date }}</span></template>
            </el-table-column>
            <el-table-column :label="t('funds.contributor')" min-width="90">
              <template #default="{ row }">
                <el-tag v-if="row.contributor" size="small" type="primary" effect="plain">{{ row.contributor }}</el-tag>
                <span v-else class="pcr-dim">—</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('funds.amount')" align="right" min-width="110">
              <template #default="{ row }"><span class="pcr-mono">{{ jpy(row.amount) }}</span></template>
            </el-table-column>
            <el-table-column :label="t('funds.rate')" align="right" width="96">
              <template #default="{ row }">
                <span class="pcr-mono">{{ row.fx_rate ? formatRate(row.fx_rate) : '—' }}</span>
                <el-tag v-if="row.fx_manual" size="small" type="warning" effect="plain" class="tag">{{ t('funds.manualTag') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('funds.cnyCost')" align="right" min-width="104">
              <template #default="{ row }"><span class="pcr-mono">{{ cny(row.cny_cost) }}</span></template>
            </el-table-column>
            <el-table-column :label="t('funds.remaining')" align="right" min-width="110">
              <template #default="{ row }">
                <div class="pcr-mono">{{ jpy(row.remaining_amount) }}</div>
                <div class="pcr-dim sub">{{ t('funds.used') }} {{ jpy(row.used_amount) }}</div>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.actions')" width="62" align="center">
              <template #default="{ row }">
                <el-button link :icon="EditPen" @click="openInjection(row)" />
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!shownInjections.length" :description="t('funds.noInjections')" :image-size="60" />
        </el-card>
      </el-col>

      <!-- 使用明细 -->
      <el-col :xs="24" :lg="12">
        <el-card class="table-card" shadow="never">
          <template #header>
            <div class="card-head">
              <span>{{ t('funds.draws') }}</span>
              <span class="pcr-dim count">{{ t('funds.drawsHint') }}</span>
            </div>
          </template>
          <el-table :data="draws" class="pcr-table" size="small" row-key="id" empty-text=" ">
            <!-- 展开行就是这个功能的核心：一笔钱吃了哪几批注资、各按什么汇率折的 -->
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="alloc">
                  <div v-for="(a, i) in row.allocations" :key="i" class="alloc-line">
                    <span class="pcr-mono pcr-dim">{{ a.inject_date }}</span>
                    <el-tag v-if="a.contributor" size="small" type="primary" effect="plain">{{ a.contributor }}</el-tag>
                    <span class="pcr-mono">{{ jpy(a.amount) }}</span>
                    <span class="pcr-dim">× {{ formatRate(a.fx_rate) }}/{{ RATE_UNIT }} =</span>
                    <span class="pcr-mono">{{ cny(a.cny_amount) }}</span>
                  </div>
                  <div v-if="row.shortfall" class="alloc-line short">
                    <span class="pcr-dim">{{ t('funds.shortfall') }}</span>
                    <span class="pcr-mono">{{ jpy(row.shortfall) }}</span>
                    <span class="pcr-dim">{{ t('funds.shortfallHint') }}</span>
                  </div>
                  <div v-if="!row.allocations.length && !row.shortfall" class="pcr-dim">{{ t('common.noData') }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('funds.drawDate')" width="104">
              <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.draw_date }}</span></template>
            </el-table-column>
            <el-table-column :label="t('funds.purpose')" min-width="150">
              <template #default="{ row }">
                <!-- 扣款要么挂在一张卡上、要么挂在一台整机上（两者都有详情页，可点进去），
                     要么是手工记的池内支出 -->
                <router-link v-if="row.card_id" :to="`/cards/${row.card_id}`" class="link" @click.stop>
                  {{ row.owner_name || row.mgmt_no }}
                </router-link>
                <router-link v-else-if="row.device_id" :to="`/devices/${row.device_id}`" class="link" @click.stop>
                  {{ row.owner_name || row.mgmt_no }}
                </router-link>
                <span v-else>{{ row.note || t('funds.cat.other') }}</span>
                <div class="pcr-dim sub">
                  <el-tag v-if="row.owner_kind" size="small" effect="plain"
                    :type="row.owner_kind === 'device' ? 'warning' : 'primary'" class="owner-tag">
                    {{ t('inv.' + row.owner_kind) }}
                  </el-tag>
                  {{ t('funds.cat.' + row.category) }}
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('funds.amount')" align="right" min-width="110">
              <template #default="{ row }"><span class="pcr-mono">{{ jpy(row.amount) }}</span></template>
            </el-table-column>
            <el-table-column :label="t('funds.cnyCost')" align="right" min-width="110">
              <template #default="{ row }">
                <div class="pcr-mono">{{ cny(row.cny_amount) }}</div>
                <div v-if="row.effective_rate" class="pcr-dim sub pcr-mono">@{{ formatRate(row.effective_rate) }}</div>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.actions')" width="62" align="center">
              <template #default="{ row }">
                <template v-if="!row.owner_kind">
                  <el-button link :icon="EditPen" @click="openDraw(row)" />
                </template>
                <el-tooltip v-else :content="t('funds.ownerDrawLocked')">
                  <el-icon class="pcr-dim"><Lock /></el-icon>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!draws.length" :description="t('funds.noDraws')" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 注资弹窗 -->
    <el-dialog v-model="injectionVisible" :title="injectionForm.id ? t('funds.editInjection') : t('funds.addInjection')" width="480px">
      <el-form :model="injectionForm" label-position="top">
        <el-form-item :label="t('funds.injectDate')">
          <el-date-picker v-model="injectionForm.inject_date" type="date" value-format="YYYY-MM-DD" class="full" @change="previewRate" />
        </el-form-item>
        <el-form-item :label="t('funds.amount') + '（' + t('currency.JPY_short') + '）'">
          <el-input-number v-model="injectionForm.amount" :min="1" :step="10000" :precision="0" :controls="false" class="full" />
        </el-form-item>
        <!-- 出资人可以现敲一个新名字：录注资的时候才想起「这笔是老李的」，不该被打断去
             别处先把人建好。后端按名字 upsert 进字典，下次就在候选里了。 -->
        <el-form-item :label="t('funds.contributor')">
          <el-select v-model="injectionForm.contributor" filterable allow-create default-first-option
            clearable class="full" :placeholder="t('funds.contributorPlaceholder')">
            <el-option v-for="name in contributorNames" :key="name" :label="name" :value="name" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="injectionForm.manual">{{ t('funds.rateManual') }}</el-checkbox>
        </el-form-item>
        <el-form-item v-if="injectionForm.manual"
          :label="t('funds.cnyPaid') + '（' + t('currency.CNY_short') + '）'">
          <el-input-number v-model="injectionForm.cny_cost" :min="0.01" :step="100" :precision="2"
            :controls="false" class="full" />
        </el-form-item>
        <!-- 汇率不给人填，由「实付人民币 ÷ 换到的日元」现算并显示出来：金额填错了单位，
             这行的数字会立刻离谱到一眼能看出来 -->
        <div v-if="manualRate" class="fx-hint">
          {{ t('funds.derivedRate') }}: {{ RATE_UNIT }} {{ t('currency.JPY_short') }} =
          {{ formatRate(manualRate) }} {{ t('currency.CNY_short') }}
          <span class="pcr-dim">（{{ t('funds.rateInverse', { rate: inverseRate(manualRate) }) }}）</span>
        </div>
        <!-- 手工模式下不显示市场牌价：它与这笔钱的真实成本无关，摆在那儿只会让人以为用的是它 -->
        <div v-else-if="!injectionForm.manual && ratePreview" class="fx-hint">
          {{ t('card.fxPreview') }}: {{ RATE_UNIT }} {{ t('currency.JPY_short') }} = {{ formatRate(ratePreview.rate) }} {{ t('currency.CNY_short') }}
          <span class="pcr-dim">（{{ ratePreview.rate_date }}{{ ratePreview.stale ? ' *' : '' }}）</span>
        </div>
        <div v-if="injectionCostPreview" class="fx-hint">
          {{ t('funds.cnyCost') }}: {{ cny(injectionCostPreview) }}
        </div>
        <el-form-item :label="t('card.note')">
          <el-input v-model="injectionForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="injectionVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveInjection">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 手工支出弹窗 -->
    <el-dialog v-model="drawVisible" :title="drawForm.id ? t('funds.editDraw') : t('funds.addDraw')" width="440px">
      <el-alert type="info" :closable="false" :title="t('funds.drawDialogHint')" class="mb" />
      <el-form :model="drawForm" label-position="top">
        <el-form-item :label="t('funds.drawDate')">
          <el-date-picker v-model="drawForm.draw_date" type="date" value-format="YYYY-MM-DD" class="full" />
        </el-form-item>
        <el-form-item :label="t('funds.amount') + '（' + t('currency.JPY_short') + '）'">
          <el-input-number v-model="drawForm.amount" :min="1" :step="1000" :precision="0" :controls="false" class="full" />
        </el-form-item>
        <el-form-item :label="t('card.note')">
          <el-input v-model="drawForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveDraw">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditPen, Lock, Minus, Plus, Refresh } from '@element-plus/icons-vue'
import { fundsApi, fxApi } from '@/api'
import { ElMessage } from '@/utils/notify'
import { RATE_UNIT, cny, formatMoney, formatRate, inverseRate, profitClass } from '@/utils/format'
import StatCard from '@/components/StatCard.vue'

const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const rebuilding = ref(false)
const summary = ref({})
const injections = ref([])
const draws = ref([])
// 按人汇总（派生自注资与分摊）与字典里的候选名字是两份：一个刚建好还没注过资的人
// 只在候选里，只看汇总的话他在下拉中就不见了。
const contributors = ref([])
const contributorNames = ref([])
// 点「按出资人」里的一行，右边的注资批次只看那个人的。null = 不筛。
// 注意 null 和 '' 不是一回事：'' 是「未指定出资人」那一档，它也能被筛。
const contributorFilter = ref(null)

const jpy = (v) => formatMoney(v, 'JPY')
const percent = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')

const shownInjections = computed(() => {
  if (contributorFilter.value === null) return injections.value
  return injections.value.filter((r) => (r.contributor || '') === contributorFilter.value)
})

// 再点一次同一行就取消筛选——这一列没有别的点击含义，不给一个「取消」的出口
// 就只能去找表头那个链接
function toggleContributorFilter(row) {
  const key = row.name || ''
  contributorFilter.value = contributorFilter.value === key ? null : key
}

function contributorRowClass({ row }) {
  return contributorFilter.value === (row.name || '') ? 'row-active' : ''
}

const statCards = computed(() => {
  const s = summary.value
  return [
    { key: 'in', label: t('funds.totalInjected'), value: jpy(s.total_injected), icon: 'Wallet', color: '#5b8cff' },
    { key: 'inCny', label: t('funds.totalInjectedCny'), value: cny(s.total_injected_cny), icon: 'Money', color: '#7c5cff' },
    { key: 'out', label: t('funds.totalDrawn'), value: jpy(s.total_drawn), icon: 'Sell', color: '#e6a23c' },
    { key: 'balance', label: t('funds.balance'), value: jpy(s.balance), icon: 'Coin', color: '#2ec4a6' },
    { key: 'balanceCny', label: t('funds.balanceCny'), value: cny(s.balance_cny), icon: 'PriceTag', color: '#3aa0ff' },
    { key: 'avg', label: t('funds.avgRate'), value: s.avg_rate ? formatRate(s.avg_rate) : '—', icon: 'TrendCharts', color: '#c471f5' }
  ]
})

// ── 数据 ────────────────────────────────────────────────────────────────
function apply(data, warnings) {
  summary.value = data.summary || {}
  injections.value = data.injections || []
  draws.value = data.draws || []
  contributors.value = data.contributors || []
  contributorNames.value = data.contributor_names || []
  ;(warnings || data.warnings || []).forEach((w) => ElMessage.warning(w))
}

async function reload() {
  loading.value = true
  try {
    apply(await fundsApi.overview())
  } finally {
    loading.value = false
  }
}

async function rebuild() {
  rebuilding.value = true
  try {
    apply(await fundsApi.rebuild())
    ElMessage.success(t('funds.rebuilt'))
  } catch { /* 拦截器已提示 */ } finally {
    rebuilding.value = false
  }
}

// ── 注资 ────────────────────────────────────────────────────────────────
const injectionVisible = ref(false)
const ratePreview = ref(null)
const injectionForm = reactive({ id: null, inject_date: null, amount: null, manual: false, cny_cost: null, contributor: null, note: null })

// 自动取牌价时先让人看到「这笔钱花了多少人民币」——注资的意义就在这个数上。
// 手工模式下这个数就是上面填的那个，不用再显示一遍。
const injectionCostPreview = computed(() => {
  if (injectionForm.manual) return null
  const rate = ratePreview.value?.rate
  if (!rate || !injectionForm.amount) return null
  return injectionForm.amount * rate / RATE_UNIT
})

// 汇率不用人填：实付人民币 ÷ 换到的日元 × 100 就是这批钱的真实汇率，存进去的也是它。
// 后端 funds.manual_rate 会照同一个算式再算一遍，这里只管让人在保存前看见。
const manualRate = computed(() => {
  if (!injectionForm.manual || !injectionForm.cny_cost || !injectionForm.amount) return null
  return injectionForm.cny_cost / injectionForm.amount * RATE_UNIT
})

function openInjection(row = null) {
  Object.assign(injectionForm, {
    id: row?.id ?? null,
    inject_date: row?.inject_date ?? new Date().toISOString().slice(0, 10),
    amount: row?.amount ?? null,
    manual: Boolean(row?.fx_manual),
    cny_cost: row?.fx_manual ? row.cny_cost : null,
    contributor: row?.contributor ?? null,
    note: row?.note ?? null
  })
  ratePreview.value = null
  injectionVisible.value = true
  previewRate()
}

async function previewRate() {
  if (!injectionForm.inject_date) { ratePreview.value = null; return }
  try {
    ratePreview.value = await fxApi.rate({ date: injectionForm.inject_date })
  } catch {
    ratePreview.value = null
  }
}

async function saveInjection() {
  if (!injectionForm.inject_date || !injectionForm.amount) {
    ElMessage.warning(t('funds.requireDateAmount'))
    return
  }
  // 勾了手工却没填金额，存下去会静悄悄地退回按牌价折算，不如挡在这里
  if (injectionForm.manual && !injectionForm.cny_cost) {
    ElMessage.warning(t('funds.requireCnyPaid'))
    return
  }
  const payload = {
    inject_date: injectionForm.inject_date,
    amount: injectionForm.amount,
    cny_cost: injectionForm.manual ? injectionForm.cny_cost : null,
    contributor: injectionForm.contributor || null,
    note: injectionForm.note
  }
  saving.value = true
  try {
    const res = injectionForm.id
      ? await fundsApi.updateInjection(injectionForm.id, payload)
      : await fundsApi.createInjection(payload)
    apply(res)
    injectionVisible.value = false
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}

// ── 手工支出 ────────────────────────────────────────────────────────────
const drawVisible = ref(false)
const drawForm = reactive({ id: null, draw_date: null, amount: null, note: null })

function openDraw(row = null) {
  Object.assign(drawForm, {
    id: row?.id ?? null,
    draw_date: row?.draw_date ?? new Date().toISOString().slice(0, 10),
    amount: row?.amount ?? null,
    note: row?.note ?? null
  })
  drawVisible.value = true
}

async function saveDraw() {
  if (!drawForm.draw_date || !drawForm.amount) {
    ElMessage.warning(t('funds.requireDateAmount'))
    return
  }
  const payload = { draw_date: drawForm.draw_date, amount: drawForm.amount, note: drawForm.note }
  saving.value = true
  try {
    const res = drawForm.id
      ? await fundsApi.updateDraw(drawForm.id, payload)
      : await fundsApi.createDraw(payload)
    apply(res)
    drawVisible.value = false
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.page-title { font-size: 20px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.stats-card { margin-bottom: 16px; }
.stats-card :deep(.el-col) { margin-bottom: 12px; }
.pool-note { font-size: 12px; line-height: 1.7; margin: 4px 0 0; }
.mt { margin-top: 10px; }
.mb { margin-bottom: 12px; }
.table-card { margin-bottom: 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.count { font-size: 12px; }
.sub { font-size: 11px; }
.tag { margin-left: 4px; transform: scale(0.85); }
.owner-tag { margin-right: 4px; transform: scale(0.85); transform-origin: left center; }
.link { color: #8fb8ff; text-decoration: none; }
.link:hover { text-decoration: underline; }
.full { width: 100% !important; }
.hint { font-size: 12px; line-height: 1.5; }
.fx-hint {
  margin: 0 0 12px;
  padding: 6px 10px;
  font-size: 12px;
  color: #b9c4d6;
  background: rgba(91, 140, 255, 0.08);
  border-radius: 6px;
}
/* 「按出资人」整行可点（点了筛注资），所以要有手型和选中态——否则那张表看着只是个
   报表，没人会去点它 */
.contrib-table :deep(.el-table__row) { cursor: pointer; }
.contrib-table :deep(.el-table__row.row-active) { background: rgba(91, 140, 255, 0.14); }
.alloc { padding: 4px 12px 8px 46px; }
.alloc-line { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 3px 0; color: #c7d0de; }
.alloc-line.short { color: #e6a23c; }
.pcr-table :deep(.el-input-number) { width: 100% !important; }

@media (max-width: 768px) {
  /* 三个操作按钮在窄屏上换行后会一长一短地错开，各占一行反而齐整，热区也够大 */
  .head-actions { width: 100%; }
  .head-actions .el-button { flex: 1 1 40%; margin-left: 0; }
  /* 这几张表每一列都是必看的（日期 / 出资人 / 金额 / 汇率 / 人民币 / 余额 / 操作），砍掉
     哪一列都会让人为了核一个数再点进别的地方，所以宁可让它横向滚——el-table 自带滚动容器，
     卡片内边距收窄一档，能多露出小半列，一眼就看得出「右边还有」。 */
  .table-card :deep(.el-card__body) { padding: 8px 6px; }
  /* 展开行里那 46px 的左缩进是对齐桌面端展开箭头用的，窄屏上等于白扔掉八分之一行宽，
     而里面恰恰是「哪批注资 × 什么汇率 = 多少人民币」这条最长的算式 */
  .alloc { padding: 4px 6px 8px 12px; }
  .alloc-line { flex-wrap: wrap; gap: 4px 8px; }
}
</style>
