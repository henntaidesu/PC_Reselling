<template>
  <div class="detail" v-loading="loading">
    <div class="detail-head">
      <el-button :icon="ArrowLeft" text @click="$router.back()">{{ t('common.close') }}</el-button>
      <div v-if="device" class="head-right">
        <AutoSaveBadge :saving="autosave.saving.value" :saved-once="autosave.savedOnce.value" />
      </div>
    </div>

    <template v-if="device">
      <div class="title-row">
        <span class="pcr-mono mgmt">{{ device.mgmt_no }}</span>
        <!-- 整机名称是自己起的，不像显卡那样能用品牌 + 型号拼出来，所以标题本身就是个
             可改的字段。平时是文字、点铅笔才变成输入框：这一行里还并着状态和草稿标记，
             常驻一个输入框会把它们挤没。没有取消——这一页所有改动都是即时保存的，
             留一个「取消」只会让人以为别处的改动也能撤回 -->
        <el-input
          v-if="editingTitle"
          ref="titleInput"
          v-model="form.title"
          class="title-input"
          size="large"
          :maxlength="TITLE_MAX"
          show-word-limit
          :placeholder="t('device.noTitle')"
          @keyup.enter="editingTitle = false"
          @keyup.esc="editingTitle = false"
          @blur="editingTitle = false"
        />
        <template v-else>
          <h2 class="model">{{ form.title || t('device.noTitle') }}</h2>
          <el-button class="title-edit" text :icon="EditPen" :title="t('device.rename')"
            @click="startEditTitle" />
        </template>
        <StatusTag :status="form.status" />
        <el-tag v-if="device.is_draft" size="small" type="warning" effect="plain">{{ t('common.draft') }}</el-tag>
      </div>

      <!-- 摘要条。切到任何一个部件都还看得见这台机器的总账——部件的售价只有对着
           「一共花了多少、还差多少回本」才有意义 -->
      <div class="summary">
        <div class="summary-item">
          <span class="summary-label">{{ t('device.cost') }}</span>
          <span class="pcr-mono summary-value">{{ cny(money.cost_total_cny) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ t('device.revenue') }}</span>
          <span class="pcr-mono summary-value">{{ cny(money.sale_cny) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ t('device.profit') }}</span>
          <span class="pcr-mono summary-value" :class="profitClass(money.profit_cny)">{{ cny(money.profit_cny) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ t('device.recovery') }}</span>
          <span class="pcr-mono summary-value">{{ money.recovery === null ? '—' : money.recovery + '%' }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ t('device.soldParts') }}</span>
          <span class="pcr-mono summary-value">{{ money.sold_count }} / {{ money.part_count }}</span>
        </div>
        <div v-if="money.settled" class="summary-flag done">{{ t('device.settledHint') }}</div>
        <el-tooltip v-else-if="money.incomplete" :content="t('card.incomplete')">
          <div class="summary-flag warn"><el-icon><WarningFilled /></el-icon>{{ t('card.incomplete') }}</div>
        </el-tooltip>
      </div>

      <!-- 二级菜单：整机 + 每个**部件类型**一页。按类型分而不是按行分，三条内存就是
           同一页里的三张卡片，而不是三个都叫「内存」的标签。
           el-tabs 只当标签条用，内容自己在下面渲染——挂在 tab-pane 里的话所有部件会
           一次性全部挂载，每个都去拉一遍图片 -->
      <div class="tabs-row">
        <el-tabs v-model="activeTab" class="part-tabs">
          <el-tab-pane name="device">
            <template #label>
              <span class="tab-label">
                {{ t('device.tabDevice') }}
                <span v-if="deviceMediaCount" class="tab-badge">{{ deviceMediaCount }}</span>
              </span>
            </template>
          </el-tab-pane>
          <el-tab-pane v-for="type in PART_TABS" :key="type" :name="type">
            <template #label>
              <span class="tab-label" :class="{ 'tab-label--blank': !partsByTab[type].some(hasPartContent) }">
                {{ t('partType.' + type) }}
                <span v-if="partsByTab[type].length > 1" class="tab-count">×{{ partsByTab[type].length }}</span>
                <span v-if="tabMediaCount(type)" class="tab-badge">{{ tabMediaCount(type) }}</span>
              </span>
            </template>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- ── 整机页 ────────────────────────────────────────────────────── -->
      <template v-if="activeTab === 'device'">
        <el-row :gutter="16">
          <el-col :xs="24" :lg="14">
            <el-card shadow="never" class="block">
              <template #header>{{ t('device.purchaseInfo') }}</template>

              <div class="fields">
                <InlineField :label="t('device.name')">
                  <el-input v-model="form.title" :maxlength="TITLE_MAX" :placeholder="t('device.noTitle')" />
                </InlineField>
                <InlineField :label="t('card.status')">
                  <el-select v-model="form.status">
                    <el-option v-for="s in statuses" :key="s" :label="t('status.' + s)" :value="s" />
                  </el-select>
                </InlineField>
                <InlineField :label="t('card.platform')">
                  <el-select v-model="form.source_platform" clearable :placeholder="t('common.unset')">
                    <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value" />
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
              </div>

              <el-divider />

              <div class="fields">
                <InlineField :label="t('card.purchaseDate')">
                  <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD"
                    :placeholder="t('common.unset')" />
                </InlineField>
                <!-- 汇率是按购入日取的快照，不给手改：改了日期，保存之后这一行自己就变了 -->
                <InlineField :label="t('card.purchaseFx')" readonly>
                  <span class="pcr-mono">{{ device.purchase_fx_rate ? formatRate(device.purchase_fx_rate) : '—' }}<span
                    v-if="device.purchase_fx_date" class="pcr-dim"> · {{ device.purchase_fx_date }}</span></span>
                </InlineField>
                <InlineField :label="t('device.purchaseAmount')">
                  <MoneyInput v-model:amount="form.purchase_amount" v-model:currency="form.purchase_currency" />
                </InlineField>
                <InlineField :label="t('card.intlShipping')">
                  <MoneyInput v-model:amount="form.intl_shipping_amount" v-model:currency="form.intl_shipping_currency" />
                </InlineField>
                <InlineField :label="t('card.fundSource')">
                  <el-select v-model="form.fund_source">
                    <el-option :label="t('card.fundOwn')" value="own" />
                    <el-option :label="t('card.fundPool')" value="pool" />
                  </el-select>
                </InlineField>
              </div>
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
          </el-col>

          <el-col :xs="24" :lg="10">
            <!-- 整机自己的照片：整机外观、铭牌、开机测试这类拍的是「这台机器」，
                 不属于任何一个部件 -->
            <el-card shadow="never" class="block">
              <template #header>
                {{ t('device.deviceMedia') }}
                <span class="pcr-dim media-hint">{{ t('device.deviceMediaHint') }}</span>
              </template>
              <MediaGallery
                owner="devices"
                :owner-id="device.id"
                :hosting-configured="hostingConfigured"
                large
                @changed="onDeviceMediaChanged"
              />
            </el-card>
          </el-col>
        </el-row>

        <!-- 部件一览：分页之后总得有一个地方能一眼看完「哪几件卖了、哪几件还空着」 -->
        <el-card shadow="never" class="block">
          <template #header>{{ t('device.partsOverview') }}</template>
          <el-table :data="form.parts" class="parts-table" @row-click="(row) => (activeTab = partTab(row.part_type))">
            <el-table-column :label="t('inv.kind')" width="110">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" type="info">{{ t('partType.' + row.part_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('inv.name')" min-width="200">
              <template #default="{ row }">
                <span v-if="hasPartContent(row)">{{ partTitle(row) }}</span>
                <span v-else class="pcr-dim">{{ t('device.blankSlot') }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('card.media')" width="90" align="center">
              <template #default="{ row }">
                <span v-if="row._media_count" class="pcr-mono">{{ row._media_count }}</span>
                <span v-else class="pcr-dim">—</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('card.saleDate')" width="120">
              <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.sale_date || '—' }}</span></template>
            </el-table-column>
            <el-table-column :label="t('card.status')" width="110">
              <template #default="{ row }">
                <StatusTag v-if="isSold(row)" :status="row.status" />
                <el-tag v-else size="small" type="info" effect="plain">{{ t('device.unsold') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('card.saleAmount')" width="130" align="right">
              <template #default="{ row }">
                <span class="pcr-mono">{{ isSold(row) ? formatMoney(row.sale_amount, row.sale_currency) : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('device.netIncome')" width="130" align="right">
              <template #default="{ row }">
                <span class="pcr-mono">{{ partNet(row) === null ? '—' : cny(partNet(row)) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-row :gutter="16">
          <el-col :xs="24" :lg="12">
            <PoolBreakdown v-if="device.fund_draws?.length" :draws="device.fund_draws" class="block" />
          </el-col>
          <el-col :xs="24" :lg="12">
            <StatusTimeline v-if="device.status_logs?.length" :logs="device.status_logs" class="block" />
          </el-col>
        </el-row>
      </template>

      <!-- ── 某一类部件的页：这一类下面每件一张卡片 ────────────────────── -->
      <template v-else>
        <DevicePartPanel
          v-for="part in tabParts"
          :key="part._uid"
          :part="part"
          :net="partNet(part)"
          :deletable="canRemovePart(part)"
          :ensure-id="() => ensurePartId(part)"
          :hosting-configured="hostingConfigured"
          @remove="removePart(part)"
          @media-changed="(n) => onPartMediaChanged(part, n)"
        />
        <!-- 加同类部件的入口放在这一类的末尾：插第二条内存时人正看着第一条，
             不该再回到顶上的菜单里去找类型。类型只在添加时定一次，之后不给改——
             类型换掉，下面的品牌、规格、售价全都对不上，不如删掉重加一件 -->
        <el-card shadow="never" class="add-card" @click="addPart(activeTab)">
          <el-icon><Plus /></el-icon>
          <span>{{ t('device.addPartOfType', { name: t('partType.' + activeTab) }) }}</span>
        </el-card>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import { ArrowLeft, EditPen, Plus, WarningFilled } from '@element-plus/icons-vue'
import { devicesApi, fundsApi, mediaApi, systemApi } from '@/api'
import { cny, formatMoney, formatRate, profitClass } from '@/utils/format'
import { DEFAULT_PART_TYPES, PART_TABS, hasPartContent, isBlankPart, partTab } from '@/constants/parts'
import { useAutoSave } from '@/composables/useAutoSave'
import { usePlatforms } from '@/composables/usePlatforms'
import { useMetaStore } from '@/stores/meta'
import AutoSaveBadge from '@/components/AutoSaveBadge.vue'
import DevicePartPanel from '@/components/DevicePartPanel.vue'
import InlineField from '@/components/InlineField.vue'
import MediaGallery from '@/components/MediaGallery.vue'
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
// 'device' 或某个部件类型（PART_TABS 里的一个）
const activeTab = ref('device')
const deviceMediaCount = ref(0)

// 名称的长度上限。与后端 DevicePayload.title 的 max_length 一致——两边不一样的话，
// 前端放进去的字后端会原地打回 422，而这一页是自动保存的，表现成「怎么改都存不上」。
const TITLE_MAX = 20
const editingTitle = ref(false)
const titleInput = ref(null)

async function startEditTitle() {
  editingTitle.value = true
  await nextTick()
  titleInput.value?.focus()
}

const statuses = computed(() => meta.enums.statuses || [])
const { platforms } = usePlatforms()
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
    // 下划线开头的字段只用于界面，不进提交载荷（见 buildPayload）。
    // _keep：这一行是真实存在的、不是摆出来的模板（见 constants/parts.js）
    _keep: false,
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

// 部件按标签页归组。散热 / 机箱这类没有自己标签页的历史类型都落在「其他」里。
const partsByTab = computed(() => {
  const map = Object.fromEntries(PART_TABS.map((type) => [type, []]))
  for (const part of form.parts) map[partTab(part.part_type)].push(part)
  return map
})
const tabParts = computed(() => partsByTab.value[activeTab.value] || [])

// 标签上的角标是这一类**所有**部件的图片数之和，不是某一件的
function tabMediaCount(type) {
  return partsByTab.value[type].reduce((n, p) => n + (p._media_count || 0), 0)
}

// 六个标准槽位每类至少留一件——一台机器不可能没有 CPU，而空槽位不落库，留着没成本。
// 「其他」是可选的，删到零也行。
function canRemovePart(part) {
  const type = partTab(part.part_type)
  return type === 'other' || partsByTab.value[type].length > 1
}

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

function partTitle(part) {
  return [part.brand, part.model, part.spec].filter(Boolean).join(' ') || '—'
}
function isSold(part) {
  const v = part.sale_amount
  return v !== null && v !== undefined && v !== ''
}

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
    part._keep = true   // 库里已经有它了，从此只有手动删除才会消失
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
    // 库里已经有这一行了：把字段清空也不该让它消失，只有点「删除该部件」才删
    item._keep = true
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

function onDeviceMediaChanged(count) {
  deviceMediaCount.value = count
  // 只传了图、一个字都没改的新设备：它这时还是草稿，离开页面会被当空记录删掉，
  // 刚传的图跟着一起没。所以传完图立刻存一次，把它转正。
  if (device.value?.is_draft) doSave().catch(() => { /* 拦截器已提示 */ })
}

// 给一个还没落盘的部件传图之前，先把这一行建出来拿到 id。
// 「想先把照片存下来」是个正当诉求，不该被「你得先填点什么」挡住。
async function ensurePartId(part) {
  if (part.id) return part.id
  part._keep = true          // 空槽位默认不提交，先钉住它
  await autosave.saveNow()
  return part.id || null
}

// 从某一类页面底部的「添加」卡进来，加的就是这一类；「其他」页加出来的是 other。
// 新卡片直接接在这一页的末尾，不跳页。
function addPart(type) {
  const part = blankPart(type)
  part._keep = true          // 手动加的就是要它，哪怕还一个字没填
  form.parts.push(part)
}

async function removePart(part) {
  const index = form.parts.indexOf(part)
  // 按钮本来就不该出现，这里再挡一道：删掉最后一件 CPU，这台机器就再也补不回来了
  if (index < 0 || !canRemovePart(part)) return
  // 摆出来的空槽位直接去掉（它本来就没存过）；真实存在的要问一声——删掉这一行，
  // 挂在它上面的图片会被数据库级联删除，点错了找不回来
  if (part.id || hasPartContent(part)) {
    try {
      await ElMessageBox.confirm(t('device.removePartConfirm'), t('device.removePart'), { type: 'warning' })
    } catch {
      return
    }
  }
  form.parts.splice(index, 1)
  // 留在当前这一页：删完接着看同类剩下的那几件，不用再点回来
}

async function load() {
  loading.value = true
  autosave.pause()
  try {
    const res = await devicesApi.get(route.params.id)
    device.value = res
    Object.assign(form, normalize(res))
    loadDeviceMediaCount()
  } finally {
    loading.value = false
  }
  // 等填充引起的那波 watch 冲刷完再开自动保存，否则一进页面就白存一遍
  await autosave.begin()
}

async function loadDeviceMediaCount() {
  try {
    const res = await mediaApi.flatList('devices', route.params.id)
    deviceMediaCount.value = (res.items || []).length
  } catch {
    deviceMediaCount.value = 0
  }
}

async function loadPoolSummary() {
  try {
    poolSummary.value = await fundsApi.summary()
  } catch {
    poolSummary.value = null
  }
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
.title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.mgmt { font-size: 13px; color: #8fb8ff; }
.model { font-size: 20px; color: #e6edf7; margin: 0; }
/* 铅笔平时淡着，鼠标扫到标题那一片才亮起来——它是个随手可用的入口，不是要人注意的按钮 */
.title-edit { color: #6f7b8e; padding: 4px; }
.title-row:hover .title-edit { color: #8fb8ff; }
.title-input { max-width: 320px; }

/* 摘要条 */
.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 28px;
  padding: 12px 16px;
  margin-bottom: 4px;
  border-radius: 8px;
  background: var(--pcr-card);
  border: 1px solid var(--pcr-border);
}
.summary-item { display: flex; flex-direction: column; gap: 2px; }
.summary-label { font-size: 12px; color: #8a94a6; }
.summary-value { font-size: 16px; color: #e6edf7; }
.summary-flag {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
}
.summary-flag.done { color: #67c23a; background: rgba(103, 194, 58, 0.1); }
.summary-flag.warn { color: #e6a23c; background: rgba(230, 162, 60, 0.1); }

/* 二级菜单 */
.tabs-row { display: flex; align-items: center; gap: 12px; }
.part-tabs { flex: 1 1 auto; min-width: 0; }
/* el-tabs 只当标签条用，内容由下面自己渲染 */
.part-tabs :deep(.el-tabs__content) { display: none; }
.part-tabs :deep(.el-tabs__header) { margin-bottom: 0; }
.part-tabs :deep(.el-tabs__nav-wrap::after) { background-color: var(--pcr-border); }
.tab-label { display: inline-flex; align-items: center; gap: 6px; }
/* 还没填过的槽位淡一档：一眼能看出哪几件是待填的模板 */
.tab-label--blank { opacity: 0.55; }
.tab-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #5b8cff;
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}
.tab-count { font-size: 11px; color: #8a94a6; }

/* 末尾的「添加同类部件」卡。做成虚线框而不是一个按钮：它和上面那几张部件卡是同一列
   东西，看起来就该是「下一张还空着的卡」 */
.add-card {
  margin-bottom: 16px;
  cursor: pointer;
  border-style: dashed;
  transition: border-color 0.15s, color 0.15s;
}
.add-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 18px;
  color: #8a94a6;
  font-size: 13px;
}
.add-card:hover { border-color: #5b8cff; }
.add-card:hover :deep(.el-card__body) { color: #8fb8ff; }

.block { margin-bottom: 16px; }
.block:first-of-type { margin-top: 16px; }
/* 两列字段。列间距比标签到输入框的 12px 明显宽，两列之间才不会糊成一片 */
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 32px; }
.block :deep(.el-divider) { margin: 10px 0; }
.media-hint { font-size: 12px; font-weight: 400; margin-left: 8px; }
.row-link { color: #8fb8ff; text-decoration: none; flex: 0 0 auto; padding: 0 4px; }
.parts-table :deep(.el-table__row) { cursor: pointer; }
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
.hint .warn { color: #e6a23c; }

@media (max-width: 1100px) {
  .fields { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 768px) {
  .tabs-row { flex-direction: column; align-items: stretch; gap: 8px; }
  .summary-flag { margin-left: 0; }
}
</style>
