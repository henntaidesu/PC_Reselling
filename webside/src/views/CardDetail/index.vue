<template>
  <!-- 显卡详情：一屏平铺。基本信息、购入、出售三块字段一直摆着（显卡一共就这十几个值，
       拆成页面来回切只会让人找不到东西），图片在右侧栏；只有资金明细和状态记录这两样
       「偶尔才看」的收进最下面的标签页卡。每个值仍然是直接可改的控件、改完自动保存。 -->
  <DetailShell :loading="loading" :ready="!!card" @close="emit('close')">
    <template #title>
      <template v-if="card">
        <!-- 封面缩略图：标题栏里最快认出「这是哪一张卡」的线索 -->
        <div class="head-cover">
          <img v-if="coverUrl" :src="coverUrl" alt="" />
          <el-icon v-else><Picture /></el-icon>
        </div>
        <h2 class="head-name">{{ [form.brand, form.model].filter(Boolean).join(' ') || t('card.noModel') }}</h2>
        <StatusTag :status="form.status" />
      </template>
    </template>

    <!-- 总账药丸：切到哪个标签页都在眼前，改售价的时候得对着成本看 -->
    <template v-if="card" #stats>
      <span class="pd-stat">
        <span class="pd-stat-k">{{ t('card.cost') }}</span>
        <b class="pd-stat-v pcr-mono">{{ cny(card.money.cost_total_cny) }}</b>
        <span class="pd-stat-sub pcr-mono">{{ jpy(card.money.cost_total_jpy) }}</span>
      </span>
      <span class="pd-stat">
        <span class="pd-stat-k">{{ t('card.revenue') }}</span>
        <b class="pd-stat-v pcr-mono">{{ cny(card.money.sale_cny) }}</b>
      </span>
      <span class="pd-stat" :class="profitTone(card.money.profit_cny)">
        <span class="pd-stat-k">{{ t('card.profit') }}</span>
        <b class="pd-stat-v pcr-mono">{{ cny(card.money.profit_cny) }}</b>
      </span>
      <span class="pd-stat">
        <span class="pd-stat-k">{{ t('card.margin') }}</span>
        <b class="pd-stat-v pcr-mono">{{ card.money.profit_margin === null ? '—' : card.money.profit_margin + '%' }}</b>
      </span>
      <el-tooltip v-if="card.money.incomplete" :content="t('card.incomplete')">
        <span class="pd-flag warn"><el-icon><WarningFilled /></el-icon>{{ t('card.incomplete') }}</span>
      </el-tooltip>
    </template>

    <template #actions>
      <AutoSaveBadge v-if="card" :saving="autosave.saving.value" :saved-once="autosave.savedOnce.value" />
    </template>

    <template v-if="card">
      <!-- ── 基本信息：flex 折行，各字段按内容给宽度（.f-*），不是等宽两列 ──────── -->
      <section class="pd-card">
        <div class="pd-card-head">
          <span class="pd-card-title">{{ t('detail.modBasic') }}</span>
          <span class="pd-badge pcr-mono">{{ t('card.mgmtNo') }} {{ card.mgmt_no }}</span>
          <span v-if="card.is_draft" class="pd-badge pd-badge--warn">{{ t('common.draft') }}</span>
        </div>
        <el-form label-position="top" size="small" class="pd-form" @submit.prevent>
          <div class="pd-row">
            <el-form-item :label="t('card.brand')" class="f-brand">
              <el-select v-model="form.brand" filterable allow-create default-first-option clearable>
                <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.name" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('card.model')" class="f-model">
              <el-select v-model="form.model" filterable allow-create default-first-option clearable>
                <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.name" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('card.coreNo')" class="f-core">
              <el-input v-model="form.core_no" />
            </el-form-item>
            <el-form-item :label="t('card.status')" class="f-status">
              <StatusSelect v-model="form.status" />
            </el-form-item>
            <!-- 序列号 30 位字母数字，给它最宽的一格才看得全 -->
            <el-form-item :label="t('card.serialNo')" class="f-serial">
              <el-input v-model="form.serial_no" class="mono-input" autocapitalize="off" autocorrect="off" spellcheck="false" />
            </el-form-item>
          </div>
          <div class="pd-row">
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
            <el-form-item :label="t('card.itemUrl')" class="f-url">
              <el-input v-model="form.item_url" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false">
                <template v-if="form.item_url" #append>
                  <a :href="form.item_url" target="_blank" rel="noopener" class="url-open" :title="t('common.detail')">↗</a>
                </template>
              </el-input>
            </el-form-item>
            <!-- 备注随内容长高，封顶四行：再高就把下面的卡挤没了 -->
            <el-form-item :label="t('card.note')" class="f-note">
              <el-input v-model="form.note" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" resize="none" />
            </el-form-item>
          </div>
        </el-form>
      </section>

      <!-- ── 购入 / 出售并排：一进一出，两边字段一一对应（日期、汇率、金额、运费），
           并排摆着正好对照着看 ──────────────────────────────────────────── -->
      <div class="pd-pair">
        <section class="pd-card">
          <div class="pd-card-head"><span class="pd-card-title">{{ t('detail.modPurchase') }}</span></div>
          <el-form label-position="top" size="small" class="pd-form pd-grid" @submit.prevent>
            <el-form-item :label="t('card.purchaseDate')">
              <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" :editable="!isTouch" />
            </el-form-item>
            <!-- 汇率是按日期取的快照，不给手改：改了日期，保存之后这一格自己就变了。
                 走资金池（已确认扣除）时显示池子的加权汇率，当日牌价放进悬浮提示作对照——
                 否则页面上的汇率 × 金额对不上总成本 -->
            <el-form-item :label="t('card.purchaseFx')">
              <el-tooltip :disabled="!purchaseFxTip" :content="purchaseFxTip" placement="top">
                <div class="pcr-ro">
                  <template v-if="card.money.from_pool && card.money.pool_fx_rate">
                    <span class="pcr-mono">{{ formatRate(card.money.pool_fx_rate) }}</span>
                    <span class="pcr-dim ro-sub">· {{ poolRateLabel }}</span>
                  </template>
                  <template v-else>
                    <span class="pcr-mono">{{ card.purchase_fx_rate ? formatRate(card.purchase_fx_rate) : '—' }}</span>
                    <span v-if="card.purchase_fx_date" class="pcr-dim ro-sub">· {{ card.purchase_fx_date }}</span>
                  </template>
                </div>
              </el-tooltip>
            </el-form-item>
            <el-form-item :label="t('card.purchaseAmount')">
              <MoneyInput v-model:amount="form.purchase_amount" v-model:currency="form.purchase_currency" />
            </el-form-item>
            <el-form-item :label="t('card.intlShipping')">
              <MoneyInput v-model:amount="form.intl_shipping_amount" v-model:currency="form.intl_shipping_currency" />
            </el-form-item>
          </el-form>
        </section>
        <section class="pd-card">
          <div class="pd-card-head"><span class="pd-card-title">{{ t('detail.modSale') }}</span></div>
          <el-form label-position="top" size="small" class="pd-form pd-grid" @submit.prevent>
            <el-form-item :label="t('card.saleDate')">
              <el-date-picker v-model="form.sale_date" type="date" value-format="YYYY-MM-DD" :editable="!isTouch" />
            </el-form-item>
            <el-form-item :label="t('card.saleFx')">
              <div class="pcr-ro">
                <span class="pcr-mono">{{ card.sale_fx_rate ? formatRate(card.sale_fx_rate) : '—' }}</span>
                <span v-if="card.sale_fx_date" class="pcr-dim ro-sub">· {{ card.sale_fx_date }}</span>
              </div>
            </el-form-item>
            <el-form-item :label="t('card.saleAmount')">
              <MoneyInput v-model:amount="form.sale_amount" v-model:currency="form.sale_currency" />
            </el-form-item>
            <el-form-item :label="t('card.domesticShipping')">
              <MoneyInput v-model:amount="form.domestic_shipping_amount" v-model:currency="form.domestic_shipping_currency" />
            </el-form-item>
          </el-form>
        </section>
      </div>
      <!-- 汇率取自哪一天、有没有回退过，都在这里说清楚；空着就是一切正常 -->
      <div v-if="card.warnings?.length" class="hint warn">
        <div v-for="(w, i) in card.warnings" :key="i">{{ w }}</div>
      </div>

      <!-- ── 标签页卡：资金明细 / 记录。吃掉剩下的高度，内容在卡里滚 ────────────── -->
      <section class="pd-card pd-tabs-card">
        <el-tabs v-model="active" class="pd-tabbar">
          <el-tab-pane name="fund">
            <template #label>
              {{ t('detail.tabFundSettle') }}<span v-if="card.fund_draws?.length" class="pd-count pcr-mono">{{ card.fund_draws.length }}</span>
            </template>
          </el-tab-pane>
          <el-tab-pane name="log">
            <template #label>
              {{ t('detail.modLog') }}<span v-if="card.status_logs?.length" class="pd-count pcr-mono">{{ card.status_logs.length }}</span>
            </template>
          </el-tab-pane>
        </el-tabs>

        <div class="pd-tab-body">
          <!-- 资金与结算：左边是钱从哪儿来（出资比例、确认扣款、扣到了哪几批注资），
               右边是这张卡的账（成本三项摊开、利润、分红） -->
          <div v-if="active === 'fund'" class="fund">
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

              <PoolBreakdown v-if="card.fund_draws?.length" class="sub-gap" :draws="card.fund_draws" />
            </div>

            <!-- 结算：成本拆成三项摊开，确认运费确实算进去了，而不是只看到一个总数 -->
            <div class="fund-side">
              <div class="pd-settle">
                <div class="pd-settle-row"><span>{{ t('card.purchaseAmount') }}</span><b class="pcr-mono">{{ cny(card.money.purchase_cny) }}</b></div>
                <div class="pd-settle-row"><span>{{ t('card.intlShipping') }}</span><b class="pcr-mono">{{ cny(card.money.intl_shipping_cny) }}</b></div>
                <div class="pd-settle-row"><span>{{ t('card.domesticShipping') }}</span><b class="pcr-mono">{{ cny(card.money.domestic_shipping_cny) }}</b></div>
                <div class="pd-settle-row pd-settle-sum"><span>{{ t('card.cost') }}</span><b class="pcr-mono">{{ cny(card.money.cost_total_cny) }}</b></div>
                <div class="pd-settle-row"><span>{{ t('card.revenue') }}</span><b class="pcr-mono">{{ cny(card.money.sale_cny) }}</b></div>
                <div class="pd-settle-row pd-settle-big">
                  <span>{{ t('card.profit') }}</span>
                  <b class="pcr-mono" :class="profitClass(card.money.profit_cny)">{{ cny(card.money.profit_cny) }}</b>
                </div>
              </div>
              <!-- 分红：利润全额按出资比例分。没卖出去时利润本身是空的，这里跟着显示「—」，
                   不拿成本当亏损分下去 -->
              <template v-if="card.dividends?.length">
                <div class="pd-sub-title sub-gap">{{ t('card.dividends') }}</div>
                <div v-for="d in card.dividends" :key="d.contributor" class="pd-settle-row">
                  <span>{{ d.contributor }} <i class="pcr-dim">{{ d.share_pct }}%</i></span>
                  <b class="pcr-mono" :class="profitClass(d.dividend_cny)">{{ cny(d.dividend_cny) }}</b>
                </div>
              </template>
            </div>
          </div>

          <template v-else-if="active === 'log'">
            <StatusTimeline v-if="card.status_logs?.length" :logs="card.status_logs" />
            <el-empty v-else :description="t('detail.noLogs')" :image-size="60" />
          </template>
        </div>
      </section>
    </template>

    <!-- ── 图片侧栏：五个分类竖排，侧栏自己滚 ─────────────────────────────── -->
    <template v-if="card" #aside>
      <div class="pd-card-head">
        <span class="pd-card-title">{{ t('detail.modMedia') }}</span>
        <span v-if="mediaCount" class="pd-count pcr-mono">{{ mediaCount }}</span>
      </div>
      <MediaManager :card-id="card.id" :hosting-configured="hostingConfigured" compact
        @changed="onMediaChanged" />
    </template>
  </DetailShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Picture, WarningFilled } from '@element-plus/icons-vue'
import { cardsApi, optionsApi, systemApi } from '@/api'
import { cny, firstImage, formatRate, jpy, profitClass } from '@/utils/format'
import { ElMessage } from '@/utils/notify'
import { useAutoSave } from '@/composables/useAutoSave'
import { usePlatforms } from '@/composables/usePlatforms'
import { useIsTouch } from '@/composables/useIsMobile'
import { useMetaStore } from '@/stores/meta'
import AutoSaveBadge from '@/components/AutoSaveBadge.vue'
import DetailShell from '@/components/DetailShell.vue'
import MediaManager from '@/components/MediaManager.vue'
import MoneyInput from '@/components/MoneyInput.vue'
import FundShares from '@/components/FundShares.vue'
import PoolBreakdown from '@/components/PoolBreakdown.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatusSelect from '@/components/StatusSelect.vue'
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
const { isTouch } = useIsTouch()

// card = 服务端快照（金额、汇率、分摊、时间线、草稿标记），form = 可编辑的那些列。
// 两者必须分开：保存的返回值要用来刷新展示部分，但绝不能回灌 form——用户在请求
// 往返的那几百毫秒里敲的字会被它覆盖掉。
const card = ref(null)
const loading = ref(false)
const hostingConfigured = ref(true)

// 最下面那张标签页卡停在哪一页。字段都平铺在上面了，这里只剩资金明细和记录
const active = ref('fund')
// 图片数单独记：侧栏标题的角标要它，而 card 快照只在保存时才刷新，传图不触发保存
const mediaCount = ref(0)
// 标题栏的封面缩略图，和列表上的封面是同一张（format.firstImage）
const coverUrl = computed(() => {
  const img = firstImage(card.value?.media)
  if (!img || img.kind !== 'image') return null
  return img.public_url + (img.public_url.includes('?') ? '&' : '?') + 'w=120'
})

const brands = computed(() => meta.brands)
const models = computed(() => meta.models)
const { platforms } = usePlatforms()
const contributorOptions = computed(() => meta.contributors)

// 顶栏利润药丸的色调：赚了绿、亏了红，算不出来（缺汇率）或刚好持平不上色
function profitTone(v) {
  if (v === null || v === undefined || Number(v) === 0) return ''
  return Number(v) > 0 ? 'is-up' : 'is-down'
}

function blankForm() {
  return {
    id: null,
    brand: null, model: null, core_no: null, serial_no: null,
    source_platform: null, seller: null, item_url: null, order_no: null,
    purchase_date: null, purchase_amount: null, purchase_currency: 'JPY',
    intl_shipping_amount: null, intl_shipping_currency: 'JPY',
    domestic_shipping_amount: null, domestic_shipping_currency: 'CNY',
    sale_date: null, sale_amount: null, sale_currency: 'CNY',
    fund_source: 'pool',
    // [{ contributor, share_pct }]，空数组 = 不指定出资人，按全池 FIFO 扣
    fund_shares: [],
    status: 'purchased', note: null
    // 汇率一律按日期自动获取，不在这里填
  }
}
const form = reactive(blankForm())

const poolCurrencyMismatch = computed(() =>
  form.purchase_currency !== 'JPY' && form.purchase_amount
)
const poolDrawn = computed(() => Boolean(card.value?.pool_confirmed_at))

const poolRateLabel = computed(() => {
  const shares = card.value?.fund_shares || []
  if (shares.length === 1) return shares[0].contributor + ' ' + t('card.poolRate')
  if (shares.length > 1) return shares.map((s) => s.contributor).join('/') + ' ' + t('card.poolRate')
  return t('card.poolRate')
})
// 走资金池时格子里摆的是池子汇率，当日牌价收进悬浮提示：半宽的格子摆不下三段字
const purchaseFxTip = computed(() => {
  const c = card.value
  if (!c?.money.from_pool || !c.money.pool_fx_rate || !c.purchase_fx_rate) return ''
  return t('card.marketRate') + ' ' + formatRate(c.purchase_fx_rate)
})
const poolBusy = ref(false)

// 确认 / 撤销都回 这张卡完整的一份（与 GET 同形），直接换掉展示数据即可。
// **不能拿它回灌表单**：请求往返那几百毫秒里敲的字会被覆盖掉。
async function togglePoolDraw(action, okKey) {
  poolBusy.value = true
  try {
    card.value = await action(form.id)
    ElMessage.success(t(okKey))
  } catch { /* 拦截器已提示 */ } finally {
    poolBusy.value = false
  }
}
const confirmPoolDraw = () => togglePoolDraw(cardsApi.confirmPoolDraw, 'card.poolDrawnOk')
const cancelPoolDraw = () => togglePoolDraw(cardsApi.cancelPoolDraw, 'card.poolUndoOk')

const autosave = useAutoSave(doSave)
watch(form, autosave.schedule, { deep: true })

async function doSave() {
  const payload = { ...form }
  delete payload.id
  const res = await cardsApi.update(form.id, payload)
  card.value = res
  await persistDict()
}

function normalize(row) {
  const out = {}
  for (const key of Object.keys(blankForm())) out[key] = row[key] ?? null
  out.id = row.id
  // 币种这几列在库里是 NOT NULL，但仍要兜一层：null 传回后端会被校验器打回，
  // 于是整条保存链失败，表现成「这张卡怎么改都存不进去」
  out.purchase_currency = row.purchase_currency || 'JPY'
  out.intl_shipping_currency = row.intl_shipping_currency || 'JPY'
  out.sale_currency = row.sale_currency || 'CNY'
  out.domestic_shipping_currency = row.domestic_shipping_currency || 'CNY'
  out.fund_source = 'pool'
  // 拷一份而不是直接引用：直接引用的话，组件改了这个数组等于改了 card 快照里的同一个
  // 对象，「服务端返回的是什么」和「表单里现在是什么」就分不开了
  out.fund_shares = (row.fund_shares || []).map((x) => ({ ...x }))
  out.status = row.status || 'purchased'
  return out
}

async function load() {
  loading.value = true
  autosave.pause()
  try {
    const res = await cardsApi.get(props.id)
    card.value = res
    mediaCount.value = res.media?.length || 0
    Object.assign(form, normalize(res))
  } finally {
    loading.value = false
  }
  // 等填充引起的那波 watch 冲刷完再开自动保存，否则一进页面就白存一遍
  await autosave.begin()
}


async function persistDict() {
  // 品牌只在「系统配置」里手动维护，这里不把现敲的品牌写进字典（免得污染清单）；
  // 型号是独立模块，现敲一个新型号会顺手补进型号字典。
  try {
    if (form.model && !models.value.some((m) => m.name === form.model)) {
      await optionsApi.createModel({ name: form.model })
      meta.reloadModels()
    }
    // 出资人不用在这里建：后端存比例时已经顺手把新名字落进字典了，这里只把候选刷新一下，
    // 否则同一次会话里换一张卡，刚敲的那个名字又不在下拉里了
    if (form.fund_shares?.some((x) => !meta.contributors.includes(x.contributor))) {
      meta.reloadContributors()
    }
  } catch { /* 字典写入失败不影响卡片本身 */ }
}

// 只传了图、一个字都没改的新卡：它这时还是草稿，离开页面会被当空卡删掉，刚传的图
// 跟着一起没。所以传完图立刻存一次，把它转正。
async function onMediaChanged() {
  if (card.value?.is_draft) {
    try { await doSave() } catch { /* 拦截器已提示 */ }
  }
  // 角标和标题栏封面跟着刷新。只换展示用的 media，不碰 form，也不整份替换 card——
  // 这一发 GET 和自动保存可能交错，整份替换会拿旧快照盖掉刚存回来的新金额
  try {
    const res = await cardsApi.get(props.id)
    mediaCount.value = res.media?.length || 0
    if (card.value) card.value = { ...card.value, media: res.media }
  } catch { /* 角标晚一点对上也无妨 */ }
}

// 关闭前把没落盘的改动存完；仍是草稿（从「新增」进来又什么都没填）就把这张空卡删掉。
// 由持有弹窗的列表页在路由守卫里 await 它——关弹窗的路径有好几条（关闭按钮、点遮罩、
// 浏览器后退、直接点侧栏去别的页），守卫是它们唯一的汇合点。
async function beforeClose() {
  autosave.pause()
  if (autosave.pending.value) await autosave.flush()
  if (card.value?.is_draft) {
    try { await cardsApi.remove(card.value.id, true) } catch { /* 删不掉就留给启动时的清理 */ }
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
.head-cover {
  flex: none;
  width: 40px;
  height: 30px;
  border-radius: 5px;
  overflow: hidden;
  background: #0e1830;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #3a4a66;
  font-size: 16px;
}
.head-cover img { width: 100%; height: 100%; object-fit: cover; }
.head-name { margin: 0; font-size: 17px; color: #e6edf7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 基本信息两行的字段宽度：基准宽度 + 上限，摆不下就折行 */
.f-brand { flex: 1 1 140px; max-width: 200px; }
.f-model { flex: 1 1 180px; max-width: 280px; }
.f-core { flex: 0 1 130px; }
.f-status { flex: 0 1 140px; }
.f-serial { flex: 1 1 230px; }
.f-platform { flex: 0 1 130px; }
.f-seller { flex: 1 1 130px; max-width: 200px; }
.f-order { flex: 0 1 170px; }
.f-url { flex: 1 1 200px; max-width: 360px; }
.f-note { flex: 1 1 200px; }

/* 只读格子里的副文字（日期、「池汇率」字样）放不下就省略，不把格子撑成两行 */
.pcr-ro { flex-wrap: nowrap; overflow: hidden; }
.ro-sub { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }

/* 资金与结算：左边资金来源，右边账。卡片窄于 640px（平板竖屏、手机）上下叠放 */
.fund { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
@container (max-width: 640px) {
  .fund { grid-template-columns: minmax(0, 1fr); }
}
.fund-main, .fund-side { min-width: 0; }
.sub-gap { margin-top: 12px; }

/* 序列号 30 位字母数字要完整看得见、0 和 O 分得清 */
.mono-input :deep(.el-input__inner) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
.url-open { color: #8fb8ff; text-decoration: none; padding: 0 4px; }
.hint { flex: none; padding: 6px 10px; font-size: 12px; line-height: 1.7; border-radius: 6px; }
.hint.warn { color: #e6a23c; background: rgba(230, 162, 60, 0.08); }

.pool-draw { display: flex; align-items: center; gap: 6px 10px; flex-wrap: wrap; }
.pool-done { color: #4ade80; font-size: 13px; }
.pool-warn { color: #e6a23c; font-size: 12px; }
.pool-draw .pd-note { margin: 0; }

/* 触屏：small 按钮只有指甲盖大 */
@media (hover: none) {
  .pool-draw :deep(.el-button) { min-height: 34px; padding: 8px 14px; }
}

@media (max-width: 768px) {
  /* 手机上一律 16px：iOS 聚焦更小的输入框会强行放大整页且不复位（同 App.vue 那条），
     scoped 的 :deep 特异度更高，得在这里自己写一遍 */
  .mono-input :deep(.el-input__inner) { font-size: 16px; }
  .head-name { font-size: 16px; }
}
</style>
