<template>
  <!-- 整机详情：与显卡详情同一副骨架（DetailShell）。基本信息和购入一直摆着，整机照片在
       右侧栏；最下面的标签页卡只放部件编辑、资金明细和记录。每个值都是直接可改的控件，
       改完自动保存。 -->
  <DetailShell :loading="loading" :ready="!!device" @close="emit('close')">
    <template #title>
      <template v-if="device">
        <h2 class="head-name">{{ form.title || t('device.noTitle') }}</h2>
        <StatusTag :status="form.status" />
      </template>
    </template>

    <!-- 总账药丸：部件的售价只有对着「一共花了多少、还差多少回本」才有意义，切到哪页都得看得见 -->
    <template v-if="device" #stats>
      <span class="pd-stat">
        <span class="pd-stat-k">{{ t('device.cost') }}</span>
        <b class="pd-stat-v pcr-mono">{{ cny(money.cost_total_cny) }}</b>
      </span>
      <span class="pd-stat">
        <span class="pd-stat-k">{{ t('device.revenue') }}</span>
        <b class="pd-stat-v pcr-mono">{{ cny(money.sale_cny) }}</b>
      </span>
      <span class="pd-stat" :class="profitTone(money.profit_cny)">
        <span class="pd-stat-k">{{ t('device.profit') }}</span>
        <b class="pd-stat-v pcr-mono">{{ cny(money.profit_cny) }}</b>
      </span>
      <span class="pd-stat">
        <span class="pd-stat-k">{{ t('device.recovery') }}</span>
        <b class="pd-stat-v pcr-mono">{{ money.recovery === null ? '—' : money.recovery + '%' }}</b>
      </span>
      <span class="pd-stat">
        <span class="pd-stat-k">{{ t('device.soldParts') }}</span>
        <b class="pd-stat-v pcr-mono">{{ money.sold_count }} / {{ money.part_count }}</b>
      </span>
      <span v-if="money.settled" class="pd-flag done">{{ t('device.settledHint') }}</span>
      <el-tooltip v-else-if="money.incomplete" :content="t('card.incomplete')">
        <span class="pd-flag warn"><el-icon><WarningFilled /></el-icon>{{ t('card.incomplete') }}</span>
      </el-tooltip>
    </template>

    <template #actions>
      <AutoSaveBadge v-if="device" :saving="autosave.saving.value" :saved-once="autosave.savedOnce.value" />
    </template>

    <template v-if="device">
      <!-- ── 基本信息：flex 折行，各字段按内容给宽度（.f-*），不是等宽两列 ──────── -->
      <section class="pd-card">
        <div class="pd-card-head">
          <span class="pd-card-title">{{ t('detail.modBasic') }}</span>
          <span class="pd-badge pcr-mono">{{ t('card.mgmtNo') }} {{ device.mgmt_no }}</span>
          <span v-if="device.is_draft" class="pd-badge pd-badge--warn">{{ t('common.draft') }}</span>
        </div>
        <el-form label-position="top" size="small" class="pd-form" @submit.prevent>
          <div class="pd-row">
            <!-- 整机名称是自己起的，不像显卡那样能用品牌 + 型号拼出来；顶栏的名字跟着它实时变 -->
            <el-form-item :label="t('device.name')" class="f-name">
              <el-input v-model="form.title" :maxlength="TITLE_MAX" show-word-limit />
            </el-form-item>
            <el-form-item :label="t('card.status')" class="f-status">
              <StatusSelect v-model="form.status" />
            </el-form-item>
            <!-- 整机的归属人，部件没单独填的都跟随它 -->
            <el-form-item :label="t('owner.label')" class="f-owner">
              <OwnerSelect v-model="form.owner" />
            </el-form-item>
            <el-form-item :label="t('card.platform')" class="f-platform">
              <el-select v-model="form.source_platform" clearable>
                <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('card.seller')" class="f-seller">
              <el-input v-model="form.seller" />
            </el-form-item>
            <el-form-item :label="t('card.orderNo')" class="f-order">
              <el-input v-model="form.order_no" autocapitalize="off" autocorrect="off" spellcheck="false" />
            </el-form-item>
          </div>
          <div class="pd-row">
            <el-form-item :label="t('card.itemUrl')" class="f-url">
              <el-input v-model="form.item_url" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false">
                <template v-if="form.item_url" #append>
                  <a :href="form.item_url" target="_blank" rel="noopener" class="url-open" :title="t('common.detail')">↗</a>
                </template>
              </el-input>
            </el-form-item>
            <!-- 备注随内容长高，封顶四行：再高就把下面的部件区挤没了 -->
            <el-form-item :label="t('card.note')" class="f-note">
              <el-input v-model="form.note" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" resize="none" />
            </el-form-item>
          </div>
        </el-form>
      </section>

      <!-- ── 购入：一笔总价买回整台，四个值排成一行 ─────────────────────────── -->
      <section class="pd-card">
        <div class="pd-card-head">
          <span class="pd-card-title">{{ t('detail.modPurchase') }}</span>
          <span class="pd-card-extra">{{ t('device.noPartCost') }}</span>
        </div>
        <el-form label-position="top" size="small" class="pd-form pd-grid purchase-grid" @submit.prevent>
          <el-form-item :label="t('card.purchaseDate')">
            <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" :editable="!isTouch" />
          </el-form-item>
          <!-- 汇率是按购入日取的快照，不给手改。走资金池（已确认扣除）时成本按被吃掉那几批
               注资的加权汇率算，这里就得显示那个数，否则汇率 × 金额对不上总成本；
               当日牌价收进悬浮提示，格子里摆不下三段字 -->
          <el-form-item :label="t('card.purchaseFx')">
            <el-tooltip :disabled="!purchaseFxTip" :content="purchaseFxTip" placement="top">
              <div class="pcr-ro">
                <template v-if="money.from_pool && money.pool_fx_rate">
                  <span class="pcr-mono">{{ formatRate(money.pool_fx_rate) }}</span>
                  <span class="pcr-dim ro-sub">· {{ poolRateLabel }}</span>
                </template>
                <template v-else>
                  <span class="pcr-mono">{{ device.purchase_fx_rate ? formatRate(device.purchase_fx_rate) : '—' }}</span>
                  <span v-if="device.purchase_fx_date" class="pcr-dim ro-sub">· {{ device.purchase_fx_date }}</span>
                </template>
              </div>
            </el-tooltip>
          </el-form-item>
          <el-form-item :label="t('device.purchaseAmount')">
            <MoneyInput v-model:amount="form.purchase_amount" v-model:currency="form.purchase_currency" />
          </el-form-item>
          <el-form-item :label="t('card.intlShipping')">
            <MoneyInput v-model:amount="form.intl_shipping_amount" v-model:currency="form.intl_shipping_currency" />
          </el-form-item>
        </el-form>
      </section>
      <div v-if="device.warnings?.length" class="hint warn">
        <div v-for="(w, i) in device.warnings" :key="i">{{ w }}</div>
      </div>

      <!-- ── 标签页卡：吃掉剩下的高度，内容在卡里滚。el-tabs 只当标签条用，内容区
           按 active 用 v-if 只挂当前那页：图片组件一挂载就去拉图 ─────────────── -->
      <section class="pd-card pd-tabs-card">
        <el-tabs v-model="active" class="pd-tabbar">
          <el-tab-pane name="parts">
            <template #label>
              {{ t('detail.modParts') }}<span v-if="filledPartCount" class="pd-count pcr-mono">{{ filledPartCount }}</span>
            </template>
          </el-tab-pane>
          <el-tab-pane name="fund">
            <template #label>
              {{ t('detail.tabFundSettle') }}<span v-if="device.fund_draws?.length" class="pd-count pcr-mono">{{ device.fund_draws.length }}</span>
            </template>
          </el-tab-pane>
          <el-tab-pane name="log">
            <template #label>
              {{ t('detail.modLog') }}<span v-if="device.status_logs?.length || device.swaps?.length" class="pd-count pcr-mono">{{ (device.status_logs?.length || 0) + (device.swaps?.length || 0) }}</span>
            </template>
          </el-tab-pane>
        </el-tabs>

        <div class="pd-tab-body" :class="{ 'pd-tab-body--split': active === 'parts' }">
          <!-- ── 部件：左边一览全部部件，右边编辑选中的那一件 ─────────────── -->
          <div v-if="active === 'parts'" class="parts">
            <div class="parts-list">
              <!-- 一行一件。没落盘的模板槽位还没有 id，key 用本地的 _uid -->
              <button v-for="row in form.parts" :key="row._uid" type="button" class="pl-row"
                :class="{ 'is-active': row._uid === selectedUid }" @click="selectedUid = row._uid">
                <PartTypeTag :type="row.part_type" />
                <span class="pl-name" :class="{ 'pcr-dim': !hasPartContent(row) }">
                  {{ hasPartContent(row) ? partTitle(row) : t('device.blankSlot') }}
                </span>
                <span v-if="row._media_count" class="pl-media pcr-mono pcr-dim">
                  <el-icon><Picture /></el-icon>{{ row._media_count }}
                </span>
                <span class="pl-money pcr-mono" :class="{ 'pl-unsold': !isSold(row) && hasPartContent(row) }">
                  {{ isSold(row) ? formatMoney(row.sale_amount, row.sale_currency) : (hasPartContent(row) ? t('device.unsold') : '') }}
                </span>
              </button>
              <!-- 加部件：先选类型。类型只在添加时定一次，之后不给改——类型换掉，品牌、规格、
                   售价全都对不上，不如删掉重加一件 -->
              <el-dropdown trigger="click" class="pl-add-wrap" @command="addPart">
                <el-button class="pl-add" size="small" :icon="Plus">{{ t('device.addPart') }}</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="type in PART_TABS" :key="type" :command="type">
                      {{ t('partType.' + type) }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div class="parts-editor">
              <DevicePartPanel
                v-if="selectedPart"
                :key="selectedPart._uid"
                :part="selectedPart"
                :net="partNet(selectedPart)"
                :deletable="canRemovePart(selectedPart)"
                :ensure-id="() => ensurePartId(selectedPart)"
                :hosting-configured="hostingConfigured"
                :device-owner="form.owner"
                @remove="removePart(selectedPart)"
                @swap="openSwap(selectedPart)"
                @media-changed="(n) => onPartMediaChanged(selectedPart, n)"
              />
              <el-empty v-else :description="t('detail.pickPart')" :image-size="60" />
            </div>
          </div>

          <!-- ── 资金与结算：左边是钱从哪儿来（出资比例、确认扣款、扣到了哪几批注资），
               右边是这台机器的账 ─────────────────────────────────────────── -->
          <div v-else-if="active === 'fund'" class="fund">
            <div class="fund-main">
              <div class="pd-sub-label">{{ t('card.fundShares') }}</div>
              <FundShares v-model="form.fund_shares" :options="contributorOptions" />

              <div class="pd-sub-label sub-gap">{{ t('card.poolDraw') }}</div>
              <div class="pool-draw">
                <template v-if="poolDrawn">
                  <span class="pool-done">{{ t('card.poolDrawn') }}</span>
                  <el-button link size="small" :loading="poolBusy" @click="cancelPoolDraw">{{ t('card.poolUndo') }}</el-button>
                </template>
                <el-button v-else type="primary" size="small" :loading="poolBusy"
                  :disabled="poolCurrencyMismatch" @click="confirmPoolDraw">
                  {{ t('card.poolConfirm') }}
                </el-button>
                <span v-if="poolCurrencyMismatch" class="pool-warn">{{ t('card.poolCurrencyWarn') }}</span>
                <span class="pd-note">{{ t('detail.poolDrawHint') }}</span>
              </div>

              <PoolBreakdown v-if="device.fund_draws?.length" class="sub-gap" :draws="device.fund_draws" />
            </div>

            <!-- 结算：国内运费是各部件发货时付的，汇总在这里；成本三项摊开，
                 确认运费确实算进去了 -->
            <div class="fund-side">
              <div class="pd-settle">
                <div class="pd-settle-row"><span>{{ t('device.purchaseAmount') }}</span><b class="pcr-mono">{{ cny(money.purchase_cny) }}</b></div>
                <div class="pd-settle-row"><span>{{ t('card.intlShipping') }}</span><b class="pcr-mono">{{ cny(money.intl_shipping_cny) }}</b></div>
                <div class="pd-settle-row"><span>{{ t('card.domesticShipping') }}</span><b class="pcr-mono">{{ cny(money.domestic_shipping_cny) }}</b></div>
                <div class="pd-settle-row pd-settle-sum"><span>{{ t('device.cost') }}</span><b class="pcr-mono">{{ cny(money.cost_total_cny) }}</b></div>
                <div class="pd-settle-row"><span>{{ t('device.revenue') }}</span><b class="pcr-mono">{{ cny(money.sale_cny) }}</b></div>
                <div class="pd-settle-row pd-settle-big">
                  <span>{{ t('device.profit') }}</span>
                  <b class="pcr-mono" :class="profitClass(money.profit_cny)">{{ cny(money.profit_cny) }}</b>
                </div>
              </div>
              <!-- 分红：盈亏全额按出资比例分。整机是一进多出，没卖完的时候这个数是「到目前
                   为止各人分到多少」，会随着部件陆续卖出往上走 -->
              <template v-if="device.dividends?.length">
                <div class="pd-sub-title sub-gap">{{ t('card.dividends') }}</div>
                <div v-for="d in device.dividends" :key="d.contributor" class="pd-settle-row">
                  <span>{{ d.contributor }} <i class="pcr-dim">{{ d.share_pct }}%</i></span>
                  <b class="pcr-mono" :class="profitClass(d.dividend_cny)">{{ cny(d.dividend_cny) }}</b>
                </div>
              </template>
            </div>
          </div>

          <!-- ── 记录 ──────────────────────────────────────────────────── -->
          <template v-else-if="active === 'log'">
            <SwapHistory v-if="device.swaps?.length" :swaps="device.swaps" />
            <StatusTimeline v-if="device.status_logs?.length" :logs="device.status_logs" />
            <el-empty v-else :description="t('detail.noLogs')" :image-size="60" />
          </template>
        </div>
      </section>
    </template>

    <!-- ── 整机照片侧栏：拍的是「这台机器」本身，不属于任何一个部件 ──────────── -->
    <template v-if="device" #aside>
      <div class="pd-card-head">
        <span class="pd-card-title">{{ t('detail.modDeviceMedia') }}</span>
      </div>
      <p class="pd-note media-hint">{{ t('device.deviceMediaHint') }}</p>
      <MediaGallery
        owner="devices"
        :owner-id="device.id"
        :hosting-configured="hostingConfigured"
        @changed="onDeviceMediaChanged"
      />
    </template>
  </DetailShell>
  <SwapDialog v-if="device && swapPart" v-model="swapVisible" mode="part" :source-id="swapPart.id"
    :source="swapSource" @done="onSwapped" />
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import { Picture, Plus, WarningFilled } from '@element-plus/icons-vue'
import { devicesApi, systemApi } from '@/api'
import { cny, formatMoney, formatRate, profitClass } from '@/utils/format'
import { ElMessage } from '@/utils/notify'
import { DEFAULT_PART_TYPES, PART_TABS, hasPartContent, isBlankPart, partTab } from '@/constants/parts'
import { useAutoSave } from '@/composables/useAutoSave'
import { useIsTouch } from '@/composables/useIsMobile'
import { usePlatforms } from '@/composables/usePlatforms'
import { useMetaStore } from '@/stores/meta'
import AutoSaveBadge from '@/components/AutoSaveBadge.vue'
import DetailShell from '@/components/DetailShell.vue'
import DevicePartPanel from '@/components/DevicePartPanel.vue'
import FundShares from '@/components/FundShares.vue'
import MediaGallery from '@/components/MediaGallery.vue'
import MoneyInput from '@/components/MoneyInput.vue'
import OwnerSelect from '@/components/OwnerSelect.vue'
import SwapDialog from '@/components/SwapDialog.vue'
import SwapHistory from '@/components/SwapHistory.vue'
import PoolBreakdown from '@/components/PoolBreakdown.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatusSelect from '@/components/StatusSelect.vue'
import PartTypeTag from '@/components/PartTypeTag.vue'
import StatusTimeline from '@/components/StatusTimeline.vue'

const { t } = useI18n()
// 详情不再是一个路由页，而是库存列表上的悬浮弹窗（views/Cards 持有它）。
// id 由列表从 ?open= 里解析出来传进来；关不关、什么时候关也由列表决定，这里只发 close。
const props = defineProps({
  id: { type: Number, required: true },
  // 整机专用：落地停在哪个部件标签上
  tab: { type: String, default: null }
})
const emit = defineEmits(['close'])
const meta = useMetaStore()
const contributorOptions = computed(() => meta.contributors)

// device = 服务端快照（金额、汇率、分摊、时间线、草稿标记），form = 可编辑的那些列。
// 与显卡详情页同一套：保存的返回值只用来刷新展示部分，绝不回灌 form——请求往返的
// 那几百毫秒里用户敲的字会被覆盖掉。
const device = ref(null)
const loading = ref(false)
const hostingConfigured = ref(true)
// 标签页卡当前停在哪一页。默认「部件」：基本信息和购入都常驻在上面，打开一台机器
// 最常做的事是录 / 改某个部件的售价
const active = ref('parts')

// 「部件」页里右边正在编辑的那一件。记本地 _uid 而不是服务端 id：模板槽位和刚加的
// 部件还没有 id，而 _uid 从载入起就有、保存回填 id 时也不变
const selectedUid = ref(null)
const selectedPart = computed(() => form.parts.find((p) => p._uid === selectedUid.value) || null)

// 名称的长度上限。与后端 DevicePayload.title 的 max_length 一致——两边不一样的话，
// 前端放进去的字后端会原地打回 422，而这一页是自动保存的，表现成「怎么改都存不上」。
const TITLE_MAX = 100

const { platforms } = usePlatforms()
const { isTouch } = useIsTouch()

// 金额要按购入日 / 各部件出售日的汇率折算，只有后端算得准，前端不自己算一遍
// （自己算必然和列表页对不上）
const money = computed(() => device.value?.money || {
  cost_total_cny: null, sale_cny: null, profit_cny: null, recovery: null,
  part_count: 0, sold_count: 0, settled: false, incomplete: false, pool_fx_rate: null
})

// 顶栏利润药丸的色调：赚了绿、亏了红，算不出来（缺汇率）或刚好持平不上色
function profitTone(v) {
  if (v === null || v === undefined || Number(v) === 0) return ''
  return Number(v) > 0 ? 'is-up' : 'is-down'
}

const poolRateLabel = computed(() => {
  const shares = device.value?.fund_shares || []
  if (shares.length === 1) return shares[0].contributor + ' ' + t('card.poolRate')
  if (shares.length > 1) return shares.map((s) => s.contributor).join('/') + ' ' + t('card.poolRate')
  return t('card.poolRate')
})
// 走资金池时格子里摆的是池子汇率，当日牌价收进悬浮提示：四分之一宽的格子摆不下三段字
const purchaseFxTip = computed(() => {
  const d = device.value
  if (!d?.money?.from_pool || !d.money.pool_fx_rate || !d.purchase_fx_rate) return ''
  return t('card.marketRate') + ' ' + formatRate(d.purchase_fx_rate)
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
    // null = 跟随整机的归属人
    owner: null,
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
    fund_source: 'pool',
    // [{ contributor, share_pct }]，空数组 = 不指定出资人，按全池 FIFO 扣
    fund_shares: [],
    owner: null,
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

// 「部件」标签上的计数是**填过内容**的件数，口径与列表里那个「未填写」的淡化完全一致
//（都走 hasPartContent）。刻意不跟 isBlankPart：那是「要不要提交给后端」的口径，摆出来的
// 模板槽位、只传了图的行都算数，可它们在人眼里就是还没录，算进去反而对不上。
const filledPartCount = computed(() => form.parts.filter(hasPartContent).length)

// 六个标准槽位每类至少留一件——一台机器不可能没有 CPU，而空槽位不落库，留着没成本。
// 「其他」是可选的，删到零也行。
function canRemovePart(part) {
  const type = partTab(part.part_type)
  return type === 'other' || partsByTab.value[type].length > 1
}

const poolCurrencyMismatch = computed(() =>
  form.purchase_currency !== 'JPY' && form.purchase_amount
)
const poolDrawn = computed(() => Boolean(device.value?.pool_confirmed_at))
const poolBusy = ref(false)

// 确认 / 撤销都回 这台设备完整的一份（与 GET 同形），直接换掉展示数据即可。
// **不能拿它回灌表单**：请求往返那几百毫秒里敲的字会被覆盖掉。
async function togglePoolDraw(action, okKey) {
  poolBusy.value = true
  try {
    device.value = await action(form.id)
    ElMessage.success(t(okKey))
  } catch { /* 拦截器已提示 */ } finally {
    poolBusy.value = false
  }
}
const confirmPoolDraw = () => togglePoolDraw(devicesApi.confirmPoolDraw, 'card.poolDrawnOk')
const cancelPoolDraw = () => togglePoolDraw(devicesApi.cancelPoolDraw, 'card.poolUndoOk')

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
  // 出资人不用在这里建：后端存比例时已经顺手把新名字落进字典了，这里只把候选刷新一下，
  // 否则同一次会话里换一台机器，刚敲的那个名字又不在下拉里了
  // 归属人同理（整机和部件上现敲的新名字）
  const owners = [form.owner, ...form.parts.map((p) => p.owner)].filter(Boolean)
  if (form.fund_shares?.some((x) => !meta.contributors.includes(x.contributor)) ||
      owners.some((n) => !meta.contributors.includes(n))) {
    meta.reloadContributors()
  }
}

function normalize(row) {
  const out = blankForm()
  for (const key of Object.keys(out)) {
    if (key === 'parts' || key === 'fund_shares') continue
    out[key] = row[key] ?? out[key]
  }
  out.id = row.id
  // 拷一份而不是直接引用：直接引用的话，组件改了这个数组等于改了 device 快照里的
  // 同一个对象，「服务端返回的是什么」和「表单里现在是什么」就分不开了
  out.fund_shares = (row.fund_shares || []).map((x) => ({ ...x }))
  // 币种与状态在库里是 NOT NULL，仍兜一层：null 传回后端会被校验器打回，
  // 于是整条保存链失败，表现成「这台机器怎么改都存不进去」
  out.purchase_currency = row.purchase_currency || 'JPY'
  out.intl_shipping_currency = row.intl_shipping_currency || 'JPY'
  out.fund_source = 'pool'
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

function onDeviceMediaChanged() {
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

// 加的部件插在同类的最后一件后面，列表里同一类始终挨在一起；没有同类的接在末尾。
// 加完直接选中它——人点「添加」就是要马上填这一件。
function addPart(type) {
  const part = blankPart(type)
  part._keep = true          // 手动加的就是要它，哪怕还一个字没填
  let at = -1
  form.parts.forEach((p, i) => { if (partTab(p.part_type) === type) at = i })
  if (at < 0) form.parts.push(part)
  else form.parts.splice(at + 1, 0, part)
  selectedUid.value = part._uid
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
  // 选中挪到原位置上的那一件（也就是原来的下一件），删的是最后一件就选新的最后一件：
  // 删完右边不至于空着，人也还停在列表的同一个位置
  const next = form.parts[Math.min(index, form.parts.length - 1)]
  selectedUid.value = next?._uid ?? null
}

// ── 置换 ──────────────────────────────────────────────────────────────
const swapVisible = ref(false)
const swapPart = ref(null)
// 对照显示用的「自己这一头」：部件的规格栏就是核心编号，归属人没填就是整机的
const swapSource = computed(() => {
  const p = swapPart.value
  if (!p) return {}
  return { brand: p.brand, model: p.model, core_no: p.spec, serial_no: p.serial_no, owner: p.owner || form.owner }
})

// 先把没落盘的改动存完再开：置换按库里的值互换，表单里还没存的序列号会被换丢
async function openSwap(part) {
  if (autosave.pending.value) {
    try { await autosave.flush() } catch { return }
  }
  swapPart.value = part
  swapVisible.value = true
}

// 部件的品牌、型号、序列号、图片都换成了对方的，整份重载，并停回刚才那一件
async function onSwapped() {
  const keepId = swapPart.value?.id
  await load()
  const hit = form.parts.find((p) => p.id === keepId)
  if (hit) selectedUid.value = hit._uid
}

async function load() {
  loading.value = true
  autosave.pause()
  try {
    const res = await devicesApi.get(props.id)
    device.value = res
    Object.assign(form, normalize(res))
    // 部件页默认选中第一件填过的（都没填就第一个槽位）。从库存列表的部件一览点进来时
    // 带着部件类型：直接选中那一类的第一件。走 partTab 归一：散热 / 机箱这类历史类型
    // 落在「其他」
    const first = form.parts.find(hasPartContent) || form.parts[0]
    selectedUid.value = first?._uid ?? null
    if (props.tab) {
      const type = partTab(props.tab)
      const hit = form.parts.find((p) => partTab(p.part_type) === type)
      if (hit) selectedUid.value = hit._uid
      active.value = 'parts'
    }
  } finally {
    loading.value = false
  }
  // 等填充引起的那波 watch 冲刷完再开自动保存，否则一进页面就白存一遍
  await autosave.begin()
}

// 关闭前把没落盘的改动存完；仍是草稿（从「新增」进来又什么都没填）就把这台空设备删掉。
// 调用方与理由同显卡详情（views/Cards 的路由守卫里 await 它）
async function beforeClose() {
  autosave.pause()
  if (autosave.pending.value) await autosave.flush()
  if (device.value?.is_draft) {
    try { await devicesApi.remove(device.value.id) } catch { /* 删不掉就留给启动时的清理 */ }
  }
}
defineExpose({ beforeClose })

onMounted(async () => {
  await meta.ensure()
  systemApi.getImageHosting()
    .then((ih) => { hostingConfigured.value = Boolean(ih.configured) })
    .catch(() => { hostingConfigured.value = false })
  load()
})
</script>

<style scoped>
/* 骨架在 DetailShell 里；卡片、紧凑表单、药丸、结算这些共用类在 App.vue 的 .pd-* */
.head-name { margin: 0; font-size: 17px; color: #e6edf7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 基本信息两行的字段宽度：基准宽度 + 上限，摆不下就折行 */
.f-name { flex: 1 1 240px; max-width: 380px; }
.f-status { flex: 0 1 140px; }
.f-owner { flex: 0 1 120px; }
.f-platform { flex: 0 1 130px; }
.f-seller { flex: 1 1 130px; max-width: 200px; }
.f-order { flex: 0 1 170px; }
.f-url { flex: 1 1 260px; max-width: 420px; }
.f-note { flex: 1 1 260px; }
.url-open { color: #8fb8ff; text-decoration: none; padding: 0 4px; }

/* 购入四个值一行排完；卡片窄了退回两列 */
.purchase-grid { --pd-cols: 4; }
@media (max-width: 1200px) {
  .purchase-grid { --pd-cols: 2; }
}
.pcr-ro { flex-wrap: nowrap; overflow: hidden; }
.ro-sub { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.hint { flex: none; padding: 6px 10px; font-size: 12px; line-height: 1.7; border-radius: 6px; }
.hint.warn { color: #e6a23c; background: rgba(230, 162, 60, 0.08); }
.media-hint { margin: 0 0 10px; }

/* ── 部件：左列表 / 右编辑区。两边各自占满高度、各自滚——部件多到十几件时列表自己滚，
   编辑区不动 ─────────────────────────────────────────────────────── */
.parts { height: 100%; display: grid; grid-template-columns: 250px minmax(0, 1fr); }
.parts-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px 8px 0;
  border-right: 1px solid var(--pcr-border);
  overflow-y: auto;
}
.parts-editor { min-width: 0; padding: 10px 0 10px 14px; overflow-y: auto; }
.pl-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 9px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.015);
  color: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}
.pl-row:hover { background: rgba(91, 140, 255, 0.06); }
.pl-row:focus-visible { outline: 2px solid var(--pcr-accent); outline-offset: -2px; }
.pl-row.is-active { border-color: rgba(91, 140, 255, 0.55); background: rgba(91, 140, 255, 0.1); }
.pl-name { flex: 1 1 auto; min-width: 0; color: #d6deea; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-media { flex: none; display: inline-flex; align-items: center; gap: 2px; font-size: 11px; }
.pl-money { flex: none; font-size: 12px; color: #e6edf7; }
/* 填了还没卖的那几件用红字标「未出售」：一台机器剩哪几件没出手，是这张列表最该一眼看到的 */
.pl-unsold { color: #f87171; }
.pl-add-wrap { margin-top: 6px; }
.pl-add { width: 100%; }

/* 资金与结算：左边资金来源，右边账。卡片窄于 640px（平板竖屏、手机）上下叠放 */
.fund { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
@container (max-width: 640px) {
  .fund { grid-template-columns: minmax(0, 1fr); }
}
.fund-main, .fund-side { min-width: 0; }
.sub-gap { margin-top: 12px; }

.pool-draw { display: flex; align-items: center; gap: 6px 10px; flex-wrap: wrap; }
.pool-done { color: #4ade80; font-size: 13px; }
.pool-warn { color: #e6a23c; font-size: 12px; }
.pool-draw .pd-note { margin: 0; }

@media (hover: none) {
  .pool-draw :deep(.el-button) { min-height: 34px; padding: 8px 14px; }
}

/* 平板竖屏：部件列表收窄，给编辑区多留地方 */
@media (min-width: 769px) and (max-width: 1200px) {
  .parts { grid-template-columns: 200px minmax(0, 1fr); }
}

/* 手机：部件页改成上下排——上面是列表、下面是编辑区，随整块一起滚 */
@media (max-width: 768px) {
  .head-name { font-size: 16px; }
  .parts { height: auto; grid-template-columns: minmax(0, 1fr); }
  .parts-list { padding: 10px 0 12px; border-right: none; border-bottom: 1px solid var(--pcr-border); overflow: visible; }
  .parts-editor { padding: 12px 0; overflow: visible; }
}
</style>
