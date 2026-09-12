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

    <el-row :gutter="16">
      <!-- 注资批次 -->
      <el-col :xs="24" :lg="12">
        <el-card class="table-card" shadow="never">
          <template #header>
            <div class="card-head">
              <span>{{ t('funds.injections') }}</span>
              <span class="pcr-dim count">{{ t('common.total', { n: injections.length }) }}</span>
            </div>
          </template>
          <el-table :data="injections" class="pcr-table" size="small" empty-text=" ">
            <el-table-column :label="t('funds.injectDate')" width="104">
              <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.inject_date }}</span></template>
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
            <el-table-column :label="t('common.actions')" width="86" align="center">
              <template #default="{ row }">
                <el-button link :icon="EditPen" @click="openInjection(row)" />
                <el-button link type="danger" :icon="Delete" @click="removeInjection(row)" />
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!injections.length" :description="t('funds.noInjections')" :image-size="60" />
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
            <el-table-column :label="t('common.actions')" width="86" align="center">
              <template #default="{ row }">
                <template v-if="!row.owner_kind">
                  <el-button link :icon="EditPen" @click="openDraw(row)" />
                  <el-button link type="danger" :icon="Delete" @click="removeDraw(row)" />
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
        <el-form-item>
          <el-checkbox v-model="injectionForm.manual">{{ t('funds.rateManual') }}</el-checkbox>
          <div class="pcr-dim hint">{{ t('funds.rateManualHint') }}</div>
        </el-form-item>
        <el-form-item v-if="injectionForm.manual" :label="t('card.fxRate')">
          <el-input-number v-model="injectionForm.fx_rate" :min="0.5" :max="20" :step="0.01"
            :precision="4" :controls="false" class="full" />
          <!-- 顺手把反向口径显示出来：填成每元 23.165 日元、或每日元 0.0432 元，这行都会立刻露馅 -->
          <div v-if="manualInverse" class="pcr-dim hint">{{ t('funds.rateInverse', { rate: manualInverse }) }}</div>
        </el-form-item>
        <div v-else-if="ratePreview" class="fx-hint">
          {{ t('card.fxPreview') }}: {{ RATE_UNIT }} {{ t('currency.JPY_short') }} = {{ formatRate(ratePreview.rate) }} {{ t('currency.CNY_short') }}
          <span class="pcr-dim">（{{ ratePreview.rate_date }}{{ ratePreview.stale ? ' *' : '' }}）</span>
        </div>
        <div v-if="injectionCostPreview" class="fx-hint">
          {{ t('funds.cnyCost') }}: {{ cny(injectionCostPreview) }}
        </div>
        <el-form-item :label="t('funds.channel')">
          <el-input v-model="injectionForm.channel" :placeholder="t('funds.channelPlaceholder')" />
        </el-form-item>
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
import { Delete, EditPen, Lock, Minus, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { fundsApi, fxApi } from '@/api'
import { ElMessage } from '@/utils/notify'
import { RATE_UNIT, cny, formatMoney, formatRate, inverseRate } from '@/utils/format'
import StatCard from '@/components/StatCard.vue'

const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const rebuilding = ref(false)
const summary = ref({})
const injections = ref([])
const draws = ref([])

const jpy = (v) => formatMoney(v, 'JPY')

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
const injectionForm = reactive({ id: null, inject_date: null, amount: null, manual: false, fx_rate: null, channel: null, note: null })

// 存进去之前先让人看到「这笔钱花了多少人民币」——注资的意义就在这个数上
const injectionCostPreview = computed(() => {
  const rate = injectionForm.manual ? injectionForm.fx_rate : ratePreview.value?.rate
  if (!rate || !injectionForm.amount) return null
  return injectionForm.amount * rate / RATE_UNIT
})

// 手填的汇率折回「1 人民币 = ? 日元」给人对一眼，不参与保存
const manualInverse = computed(() => (injectionForm.manual ? inverseRate(injectionForm.fx_rate) : null))

function openInjection(row = null) {
  Object.assign(injectionForm, {
    id: row?.id ?? null,
    inject_date: row?.inject_date ?? new Date().toISOString().slice(0, 10),
    amount: row?.amount ?? null,
    manual: Boolean(row?.fx_manual),
    fx_rate: row?.fx_manual ? row.fx_rate : null,
    channel: row?.channel ?? null,
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
  const payload = {
    inject_date: injectionForm.inject_date,
    amount: injectionForm.amount,
    fx_rate: injectionForm.manual ? injectionForm.fx_rate : null,
    channel: injectionForm.channel,
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

async function removeInjection(row) {
  try {
    await ElMessageBox.confirm(t('funds.deleteInjectionConfirm'), t('common.delete'), { type: 'warning' })
  } catch { return }
  try {
    apply(await fundsApi.removeInjection(row.id))
    ElMessage.success(t('common.deleted'))
  } catch { /* 拦截器已提示 */ }
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

async function removeDraw(row) {
  try {
    await ElMessageBox.confirm(t('funds.deleteDrawConfirm'), t('common.delete'), { type: 'warning' })
  } catch { return }
  try {
    apply(await fundsApi.removeDraw(row.id))
    ElMessage.success(t('common.deleted'))
  } catch { /* 拦截器已提示 */ }
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
.alloc { padding: 4px 12px 8px 46px; }
.alloc-line { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 3px 0; color: #c7d0de; }
.alloc-line.short { color: #e6a23c; }
.pcr-table :deep(.el-input-number) { width: 100% !important; }
</style>
