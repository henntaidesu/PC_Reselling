<template>
  <div class="detail" v-loading="loading">
    <div class="detail-head">
      <el-button :icon="ArrowLeft" text @click="$router.back()">{{ t('common.close') }}</el-button>
      <div v-if="device" class="head-right">
        <AutoSaveBadge :saving="autosave.saving.value" :saved-once="autosave.savedOnce.value" />
        <el-button :icon="Refresh" @click="refreshFx">{{ t('card.fxRefresh') }}</el-button>
      </div>
    </div>

    <template v-if="device">
      <div class="title-row">
        <span class="pcr-mono mgmt">{{ device.mgmt_no }}</span>
        <h2 class="model">{{ form.title || t('device.noTitle') }}</h2>
        <StatusTag :status="form.status" />
        <el-tag v-if="device.is_draft" size="small" type="warning" effect="plain">{{ t('common.draft') }}</el-tag>
        <span class="pcr-dim parts-count">
          {{ t('device.soldParts') }} <b class="pcr-mono">{{ money.sold_count }} / {{ money.part_count }}</b>
        </span>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="9">
          <!-- 采购侧。整机只有一笔总价，出售价在右边的部件里各自填 -->
          <el-card shadow="never" class="info-card">
            <template #header>{{ t('device.purchaseInfo') }}</template>

            <InlineField :label="t('device.name')">
              <el-input v-model="form.title" :placeholder="t('device.noTitle')" />
            </InlineField>
            <InlineField :label="t('card.status')">
              <el-select v-model="form.status">
                <el-option v-for="s in statuses" :key="s" :label="t('status.' + s)" :value="s" />
              </el-select>
            </InlineField>

            <el-divider />

            <InlineField :label="t('card.platform')">
              <el-select v-model="form.source_platform" clearable :placeholder="t('common.unset')">
                <el-option v-for="p in platforms" :key="p" :label="t('platform.' + p)" :value="p" />
              </el-select>
            </InlineField>
            <InlineField :label="t('card.seller')">
              <el-input v-model="form.seller" :placeholder="t('common.unset')" />
            </InlineField>
            <InlineField :label="t('card.orderNo')">
              <el-input v-model="form.order_no" :placeholder="t('common.unset')" />
            </InlineField>
            <InlineField :label="t('card.itemUrl')">
              <el-input v-model="form.item_url" placeholder="https://" />
              <a v-if="form.item_url" :href="form.item_url" target="_blank" class="row-link"
                :title="t('common.detail')">↗</a>
            </InlineField>

            <el-divider />

            <InlineField :label="t('card.purchaseDate')">
              <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD"
                :placeholder="t('common.unset')" />
            </InlineField>
            <InlineField :label="t('device.purchaseAmount')">
              <MoneyInput v-model:amount="form.purchase_amount" v-model:currency="form.purchase_currency" />
            </InlineField>
            <InlineField :label="t('card.intlShipping')">
              <MoneyInput v-model:amount="form.intl_shipping_amount" v-model:currency="form.intl_shipping_currency" />
            </InlineField>
            <!-- 汇率是按购入日取的快照，不给手改：改了日期，保存之后这一行自己就变了 -->
            <InlineField :label="t('card.purchaseFx')" readonly>
              <span class="pcr-mono">{{ device.purchase_fx_rate ? formatRate(device.purchase_fx_rate) : '—' }}<span
                v-if="device.purchase_fx_date" class="pcr-dim"> · {{ device.purchase_fx_date }}</span></span>
            </InlineField>
            <InlineField :label="t('card.fundSource')">
              <el-select v-model="form.fund_source">
                <el-option :label="t('card.fundOwn')" value="own" />
                <el-option :label="t('card.fundPool')" value="pool" />
              </el-select>
            </InlineField>
            <div v-if="usePool" class="hint">
              <div>{{ t('device.fundPoolHint') }}</div>
              <div v-if="poolSummary">
                {{ t('card.poolBalance') }} <b class="pcr-mono">{{ jpy(poolSummary.balance) }}</b>
              </div>
              <div v-if="poolCurrencyMismatch" class="warn">{{ t('card.poolCurrencyWarn') }}</div>
              <div v-if="poolCost !== null">
                {{ t('card.poolCost') }}: <b class="pcr-mono">{{ cny(poolCost) }}</b>
                <span v-if="money.pool_fx_rate" class="pcr-dim">（{{ t('card.poolRate') }}
                  {{ formatRate(money.pool_fx_rate) }}）</span>
              </div>
            </div>

            <el-divider />

            <InlineField :label="t('card.note')" stack>
              <el-input v-model="form.note" type="textarea" :rows="2" :placeholder="t('common.unset')" />
            </InlineField>

            <div v-if="device.warnings?.length" class="hint warn">
              <div v-for="(w, i) in device.warnings" :key="i">{{ w }}</div>
            </div>
          </el-card>

          <!-- 合计。部件没卖完时「盈亏」只是目前收回了多少，所以回本率与它并列 -->
          <el-card shadow="never" class="profit-card">
            <div class="profit-row"><span>{{ t('device.cost') }}</span><b class="pcr-mono">{{ cny(money.cost_total_cny) }}</b></div>
            <div class="profit-row"><span>{{ t('device.revenue') }}</span><b class="pcr-mono">{{ cny(money.sale_cny) }}</b></div>
            <div class="profit-row big">
              <span>{{ t('device.profit') }}</span>
              <b class="pcr-mono" :class="profitClass(money.profit_cny)">{{ cny(money.profit_cny) }}</b>
            </div>
            <div class="profit-row"><span>{{ t('device.recovery') }}</span><b class="pcr-mono">{{ money.recovery === null ? '—' : money.recovery + '%' }}</b></div>
            <div class="profit-row"><span>{{ t('device.soldParts') }}</span><b class="pcr-mono">{{ money.sold_count }} / {{ money.part_count }}</b></div>
            <div v-if="money.settled" class="hint done">{{ t('device.settledHint') }}</div>
            <el-alert v-if="money.incomplete" :title="t('card.incomplete')" type="warning" :closable="false" show-icon class="mt" />
          </el-card>

          <PoolBreakdown v-if="device.fund_draws?.length" :draws="device.fund_draws" class="block" />
          <StatusTimeline v-if="device.status_logs?.length" :logs="device.status_logs" class="block" />
        </el-col>

        <el-col :xs="24" :lg="15">
          <el-card shadow="never" class="parts-card">
            <template #header>
              <div class="parts-head">
                <span>{{ t('device.parts') }}</span>
                <span class="pcr-dim parts-hint">{{ t('device.partsHint') }}</span>
              </div>
            </template>

            <DevicePartCard
              v-for="(part, index) in form.parts"
              :key="part._uid"
              :part="part"
              :net="partNet(part)"
              :hosting-configured="hostingConfigured"
              @remove="removePart(index)"
              @media-changed="(n) => onPartMediaChanged(part, n)"
            />

            <!-- 类型只在这里选一次，加进来之后那一行就不再能改类型了——一行的类型换掉，
                 它下面的品牌、规格、售价全都对不上，与其允许改不如删掉重加一行 -->
            <div class="add-part">
              <el-select v-model="newPartType" class="add-part-select" :placeholder="t('device.choosePartType')">
                <el-option v-for="type in partTypes" :key="type" :label="t('partType.' + type)" :value="type" />
              </el-select>
              <el-button type="primary" plain :icon="Plus" :disabled="!newPartType" @click="addChosenPart">
                {{ t('device.addPart') }}
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import { ArrowLeft, Plus, Refresh } from '@element-plus/icons-vue'
import { devicesApi, fundsApi, systemApi } from '@/api'
import { ElMessage } from '@/utils/notify'
import { cny, formatMoney, formatRate, profitClass } from '@/utils/format'
import { DEFAULT_PART_TYPES, isBlankPart } from '@/constants/parts'
import { useAutoSave } from '@/composables/useAutoSave'
import { useMetaStore } from '@/stores/meta'
import AutoSaveBadge from '@/components/AutoSaveBadge.vue'
import DevicePartCard from '@/components/DevicePartCard.vue'
import InlineField from '@/components/InlineField.vue'
import MoneyInput from '@/components/MoneyInput.vue'
import PoolBreakdown from '@/components/PoolBreakdown.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatusTimeline from '@/components/StatusTimeline.vue'

const { t } = useI18n()
const route = useRoute()
const meta = useMetaStore()

// device = 服务端快照（金额、汇率、分摊、时间线、草稿标记），form = 可编辑的那些列。
// 与显卡详情页同一套：保存的返回值只用来刷新展示部分，绝不回灌 form——请求往返的
// 那几百毫秒里用户敲的字会被覆盖掉。
const device = ref(null)
const loading = ref(false)
const hostingConfigured = ref(true)
const poolSummary = ref(null)
const newPartType = ref(null)

const statuses = computed(() => meta.enums.statuses || [])
const platforms = computed(() => meta.enums.source_platforms || [])
const partTypes = computed(() =>
  meta.enums.device_part_types?.length
    ? meta.enums.device_part_types
    : ['cpu', 'gpu', 'ram', 'disk', 'motherboard', 'psu', 'cooler', 'case', 'other']
)
// 金额要按购入日 / 各部件出售日的汇率折算，只有后端算得准，前端不自己算一遍
// （自己算必然和列表页对不上）
const money = computed(() => device.value?.money || {
  cost_total_cny: null, sale_cny: null, profit_cny: null, recovery: null,
  part_count: 0, sold_count: 0, settled: false, incomplete: false, pool_fx_rate: null
})

// 部件行的本地唯一键。v-for 不能拿数组下标当 key——删掉中间一条时，后面每条的 key
// 都会平移到上一条的输入框上，正在编辑的内容会跳到别的行去。
let uid = 0

function blankPart(partType = 'other') {
  return {
    // 服务端 id：存过的部件带着它，后端据此原地更新。图片挂在这个 id 上，所以它必须
    // 一路带回去，不能每次保存都当新行插一遍。
    id: null,
    _uid: ++uid,
    // 下划线开头的字段只用于界面，不进提交载荷（见 buildPayload）
    _media_count: 0,
    part_type: partType,
    brand: null, model: null, spec: null, serial_no: null,
    sale_date: null, sale_amount: null, sale_currency: 'CNY',
    domestic_shipping_amount: null, domestic_shipping_currency: 'CNY',
    status: 'purchased', note: null
  }
}

function blankForm() {
  return {
    id: null,
    title: null,
    source_platform: null, seller: null, item_url: null, order_no: null,
    purchase_date: null, purchase_amount: null, purchase_currency: 'JPY',
    intl_shipping_amount: null, intl_shipping_currency: 'JPY',
    fund_source: 'own',
    status: 'purchased', note: null,
    parts: []
  }
}
const form = reactive(blankForm())

const usePool = computed(() => form.fund_source === 'pool')
const poolCurrencyMismatch = computed(() =>
  usePool.value && form.purchase_currency !== 'JPY' && form.purchase_amount
)
// 这台设备实际折了多少人民币：要按 FIFO 吃到的批次算，前端算不出来，取后端返回值
const poolCost = computed(() => {
  const m = money.value
  if (!m.from_pool) return null
  const parts = [m.purchase_cny, m.intl_shipping_cny].filter((v) => v !== null && v !== undefined)
  return parts.length ? parts.reduce((a, b) => a + b, 0) : null
})
const jpy = (v) => formatMoney(v, 'JPY')

const autosave = useAutoSave(doSave)
watch(form, autosave.schedule, { deep: true })

function buildPayload(submittedParts) {
  const payload = {}
  for (const [key, value] of Object.entries(form)) {
    if (key === 'id' || key === 'parts') continue
    payload[key] = value
  }
  // 提交的数组就是这台设备**当前的全部部件**：带 id 的后端原地更新，没 id 的新插，
  // 没出现在这里的按「已删除」处理。下划线开头的字段只用于界面，不发给后端；
  // sort_order 用下标，插入 / 删除后不必自己维护。
  payload.parts = submittedParts.map((part, index) => {
    const out = { sort_order: index }
    for (const [key, value] of Object.entries(part)) {
      if (!key.startsWith('_')) out[key] = value
    }
    return out
  })
  return payload
}

// 保存后把后端分配的部件 id 贴回表单行上。不贴的话下一次保存这些行又是「没 id 的新
// 行」，后端会插一遍新的、删掉旧的，刚传的图就跟着旧行级联没了。
// 按对象引用配对而不是重新过滤一遍：await 期间用户可能又填了某个空槽位，重新过滤会
// 多出一行，后面每一行都错位一格，id 就贴到别人身上去了。
function mergePartIds(submittedParts, result) {
  const returned = result?.parts || []
  submittedParts.forEach((part, index) => {
    const server = returned[index]
    if (!server) return
    part.id = server.id
    part._media_count = server.media_count ?? part._media_count ?? 0
  })
}

async function doSave() {
  // 先定下这次提交的是哪几行（对象引用），保存回来后按同一批引用贴 id
  const submitted = form.parts.filter((part) => !isBlankPart(part))
  const res = await devicesApi.update(form.id, buildPayload(submitted))
  device.value = res
  await autosave.silently(() => mergePartIds(submitted, res))
  // 这台设备的扣款改动了池子余额，顺手刷一次；不走资金池就没必要多打这个请求
  if (form.fund_source === 'pool') loadPoolSummary()
}

function normalize(row) {
  const out = blankForm()
  for (const key of Object.keys(out)) {
    if (key === 'parts') continue
    out[key] = row[key] ?? out[key]
  }
  out.id = row.id
  // 币种与状态在库里是 NOT NULL，仍兜一层：null 传回后端会被校验器打回，
  // 于是整条保存链失败，表现成「这台机器怎么改都存不进去」
  out.purchase_currency = row.purchase_currency || 'JPY'
  out.intl_shipping_currency = row.intl_shipping_currency || 'JPY'
  out.fund_source = row.fund_source || 'own'
  out.status = row.status || 'purchased'

  // 只挑表单认识的字段：服务端行上还有 money / 汇率快照等，整份铺回表单会被原样发回
  // 后端（虽被忽略，但载荷里多一堆没人读的字段，调起来也难看）
  const saved = (row.parts || []).map((part) => {
    const item = blankPart(part.part_type)
    for (const key of Object.keys(item)) {
      if (!key.startsWith('_') && key in part) item[key] = part[key] ?? item[key]
    }
    item.id = part.id ?? null
    item.sale_currency = part.sale_currency || 'CNY'
    item.domestic_shipping_currency = part.domestic_shipping_currency || 'CNY'
    item.status = part.status || 'purchased'
    item._media_count = part.media_count ?? 0
    return item
  })
  // 详情页上也摆齐六个标准槽位：这台机器当初没录显卡，不代表之后不想补录，而空槽位
  // 不会被保存，摆着不会污染数据。已有的部件按标准顺序归组，非标准类型（散热 / 机箱
  // / 其他）排在最后。
  out.parts = []
  for (const type of DEFAULT_PART_TYPES) {
    const rows = saved.filter((p) => p.part_type === type)
    out.parts.push(...(rows.length ? rows : [blankPart(type)]))
  }
  out.parts.push(...saved.filter((p) => !DEFAULT_PART_TYPES.includes(p.part_type)))
  return out
}

// 单个部件折人民币后的净收入，取自上次保存的返回值。按 id 对，不按下标——下标会被
// 空槽位和刚删掉的行错开，一错就把上一行的钱显示到这一行上。
function partNet(part) {
  if (!part?.id) return null
  return device.value?.parts?.find((p) => p.id === part.id)?.money?.net_cny ?? null
}

// 图片增删只改显示用的角标，不该触发一次整机保存
function onPartMediaChanged(part, count) {
  autosave.silently(() => { part._media_count = count })
}

function addChosenPart() {
  if (!newPartType.value) return
  form.parts.push(blankPart(newPartType.value))
  newPartType.value = null
}

async function removePart(index) {
  const part = form.parts[index]
  if (!part) return
  // 空槽位直接去掉（它本来就没存过）；有内容的要问一声——删掉这一行，挂在它上面的
  // 图片会被数据库级联删除，点错了找不回来
  if (!isBlankPart(part)) {
    try {
      await ElMessageBox.confirm(t('device.removePartConfirm'), t('device.removePart'), { type: 'warning' })
    } catch {
      return
    }
  }
  form.parts.splice(index, 1)
}

async function load() {
  loading.value = true
  autosave.pause()
  try {
    const res = await devicesApi.get(route.params.id)
    device.value = res
    Object.assign(form, normalize(res))
  } finally {
    loading.value = false
  }
  // 等填充引起的那波 watch 冲刷完再开自动保存，否则一进页面就白存一遍
  await autosave.begin()
}

async function loadPoolSummary() {
  try {
    poolSummary.value = await fundsApi.summary()
  } catch {
    poolSummary.value = null
  }
}

async function refreshFx() {
  try {
    const res = await devicesApi.refreshFx(device.value.id)
    device.value = res
    if (res.warnings?.length) res.warnings.forEach((w) => ElMessage.warning(w))
    else ElMessage.success(t('card.fxRefreshed'))
  } catch { /* 拦截器已提示 */ }
}

// 离开前把没落盘的改动存完；仍是草稿（从「新增」进来又什么都没填）就把这台空设备删掉
onBeforeRouteLeave(async () => {
  autosave.pause()
  if (autosave.pending.value) await autosave.flush()
  if (device.value?.is_draft) {
    try { await devicesApi.remove(device.value.id) } catch { /* 删不掉就留给启动时的清理 */ }
  }
})

onMounted(async () => {
  await meta.ensure()
  loadPoolSummary()
  systemApi.getImageHosting()
    .then((ih) => { hostingConfigured.value = Boolean(ih.configured) })
    .catch(() => { hostingConfigured.value = false })
  load()
})
</script>

<style scoped>
.detail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.head-right { display: flex; align-items: center; gap: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.mgmt { font-size: 13px; color: #8fb8ff; }
.model { font-size: 20px; color: #e6edf7; margin: 0; }
.parts-count { font-size: 12px; }
.info-card, .profit-card, .parts-card { margin-bottom: 16px; }
.block { margin-bottom: 16px; }
.info-card :deep(.el-divider) { margin: 10px 0; }
.row-link { color: #8fb8ff; text-decoration: none; flex: 0 0 auto; padding: 0 4px; }
.parts-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.parts-hint { font-size: 12px; font-weight: 400; }
.hint {
  margin: 4px 0 8px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.7;
  color: #b9c4d6;
  background: rgba(91, 140, 255, 0.08);
  border-radius: 6px;
}
.hint.warn { color: #e6a23c; background: rgba(230, 162, 60, 0.08); }
.hint.done { background: rgba(103, 194, 58, 0.1); }
.hint .warn { color: #e6a23c; }
.profit-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; }
.profit-row span { color: #8a94a6; }
.profit-row b { color: #e6edf7; font-size: 15px; }
.profit-row.big b { font-size: 22px; }
.mt { margin-top: 10px; }
.add-part {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px dashed #3a4a66;
  border-radius: 10px;
  padding: 14px;
  background: rgba(91, 140, 255, 0.03);
}
.add-part-select { width: 180px !important; flex: 0 0 180px; }
</style>
