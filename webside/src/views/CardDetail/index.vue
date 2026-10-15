<template>
  <!-- 显卡详情：弹窗里的定高骨架（DetailShell），内容拆成五个模块，一次只摆一个。
       每个值仍然是直接可改的控件、改完自动保存——「详情就是编辑界面」这一条没变，
       变的只是排法：原来是一长列字段要往下拉，现在每个模块按一屏放得下来排。 -->
  <DetailShell v-model="active" :modules="modules" :loading="loading" @close="emit('close')">
    <template #title>
      <template v-if="card">
        <!-- 封面缩略图：标题栏里最快认出「这是哪一张卡」的线索 -->
        <div class="head-cover">
          <img v-if="coverUrl" :src="coverUrl" alt="" />
          <el-icon v-else><Picture /></el-icon>
        </div>
        <div class="head-text">
          <div class="head-line">
            <h2 class="head-name">{{ [form.brand, form.model].filter(Boolean).join(' ') || t('card.noModel') }}</h2>
            <StatusTag :status="form.status" />
            <el-tag v-if="card.is_draft" size="small" type="warning" effect="plain">{{ t('common.draft') }}</el-tag>
          </div>
          <div class="head-sub pcr-dim">
            <span class="pcr-mono">{{ card.mgmt_no }}</span>
            <template v-if="form.core_no"> · {{ form.core_no }}</template>
          </div>
        </div>
      </template>
    </template>
    <template #actions>
      <AutoSaveBadge v-if="card" :saving="autosave.saving.value" :saved-once="autosave.savedOnce.value" />
    </template>

    <!-- 摘要条：总账一直在眼前，切到哪个模块都看得见 -->
    <template v-if="card" #summary>
      <div class="sum-item">
        <span class="sum-label">{{ t('card.cost') }}</span>
        <b class="pcr-mono">{{ cny(card.money.cost_total_cny) }}</b>
        <span class="sum-sub pcr-mono pcr-dim">{{ jpy(card.money.cost_total_jpy) }}</span>
      </div>
      <div class="sum-item">
        <span class="sum-label">{{ t('card.revenue') }}</span>
        <b class="pcr-mono">{{ cny(card.money.sale_cny) }}</b>
      </div>
      <div class="sum-item">
        <span class="sum-label">{{ t('card.profit') }}</span>
        <b class="pcr-mono sum-big" :class="profitClass(card.money.profit_cny)">{{ cny(card.money.profit_cny) }}</b>
      </div>
      <div class="sum-item">
        <span class="sum-label">{{ t('card.margin') }}</span>
        <b class="pcr-mono">{{ card.money.profit_margin === null ? '—' : card.money.profit_margin + '%' }}</b>
      </div>
      <el-tooltip v-if="card.money.incomplete" :content="t('card.incomplete')">
        <span class="sum-flag"><el-icon><WarningFilled /></el-icon>{{ t('card.incomplete') }}</span>
      </el-tooltip>
    </template>

    <template v-if="card">
      <!-- ── 基本信息 ──────────────────────────────────────────────── -->
      <el-form v-if="active === 'basic'" label-position="top" class="pcr-form" @submit.prevent>
        <el-form-item :label="t('card.brand')">
          <el-select v-model="form.brand" filterable allow-create default-first-option clearable>
            <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('card.model')">
          <el-select v-model="form.model" filterable allow-create default-first-option clearable>
            <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('card.coreNo')">
          <el-input v-model="form.core_no" />
        </el-form-item>
        <el-form-item :label="t('card.status')">
          <StatusSelect v-model="form.status" />
        </el-form-item>
        <!-- 序列号 30 位字母数字，占满一行才看得全 -->
        <el-form-item :label="t('card.serialNo')" class="pcr-span-2">
          <el-input v-model="form.serial_no" class="mono-input" autocapitalize="off" autocorrect="off" spellcheck="false" />
        </el-form-item>
        <el-form-item :label="t('card.note')" class="pcr-span-2">
          <el-input v-model="form.note" type="textarea" :rows="5" resize="none" />
        </el-form-item>
      </el-form>

      <!-- ── 购入（含资金）：钱从哪儿来和花了多少是同一件事，放在一页里对着看。
           左边是购入字段，下面接出资比例与确认扣款；右边是这笔钱实际扣到了哪几批注资、
           按什么汇率折的，以及分红 ─────────────────────────────────── -->
      <div v-else-if="active === 'purchase'" class="split">
        <div class="split-main">
          <el-form label-position="top" class="pcr-form" @submit.prevent>
            <el-form-item :label="t('card.platform')">
              <el-select v-model="form.source_platform" clearable>
                <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('card.seller')">
              <el-input v-model="form.seller" />
            </el-form-item>
            <el-form-item :label="t('card.orderNo')">
              <el-input v-model="form.order_no" />
            </el-form-item>
            <el-form-item :label="t('card.itemUrl')">
              <el-input v-model="form.item_url" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false">
                <template v-if="form.item_url" #append>
                  <a :href="form.item_url" target="_blank" rel="noopener" class="url-open" :title="t('common.detail')">↗</a>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item :label="t('card.purchaseDate')">
              <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" :editable="!isTouch" />
            </el-form-item>
            <!-- 汇率是按日期取的快照，不给手改：改了日期，保存之后这一格自己就变了。
                 走资金池（已确认扣除）时显示池子的加权汇率，当日牌价降为小字作对照——
                 否则页面上的汇率 × 金额对不上总成本 -->
            <el-form-item :label="t('card.purchaseFx')">
              <div class="pcr-ro">
                <template v-if="card.money.from_pool && card.money.pool_fx_rate">
                  <span class="pcr-mono">{{ formatRate(card.money.pool_fx_rate) }}</span>
                  <span class="pcr-dim">· {{ poolRateLabel }}</span>
                  <span v-if="card.purchase_fx_rate" class="pcr-dim">· {{ t('card.marketRate') }} {{ formatRate(card.purchase_fx_rate) }}</span>
                </template>
                <template v-else>
                  <span class="pcr-mono">{{ card.purchase_fx_rate ? formatRate(card.purchase_fx_rate) : '—' }}</span>
                  <span v-if="card.purchase_fx_date" class="pcr-dim">· {{ card.purchase_fx_date }}</span>
                </template>
              </div>
            </el-form-item>
            <el-form-item :label="t('card.purchaseAmount')">
              <MoneyInput v-model:amount="form.purchase_amount" v-model:currency="form.purchase_currency" />
            </el-form-item>
            <el-form-item :label="t('card.intlShipping')">
              <MoneyInput v-model:amount="form.intl_shipping_amount" v-model:currency="form.intl_shipping_currency" />
            </el-form-item>
            <!-- 汇率取自哪一天、有没有回退过，都在这里说清楚；空着就是一切正常 -->
            <div v-if="card.warnings?.length" class="hint warn pcr-span-2">
              <div v-for="(w, i) in card.warnings" :key="i">{{ w }}</div>
            </div>
          </el-form>
          <h4 class="pcr-sec-title sec-gap">{{ t('detail.modFund') }}</h4>
          <div class="sub-label">{{ t('card.fundShares') }}</div>
          <FundShares v-model="form.fund_shares" :options="contributorOptions" />

          <div class="sub-label sub-gap">{{ t('card.poolDraw') }}</div>
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
          </div>
          <p class="pcr-dim small">{{ t('detail.poolDrawHint') }}</p>
        </div>
        <div class="split-side">
          <PoolBreakdown v-if="card.fund_draws?.length" :draws="card.fund_draws" />
          <el-empty v-else :description="t('detail.noPool')" :image-size="60" />
          <!-- 分红：利润全额按出资比例分。没卖出去时利润本身是空的，这里跟着显示「—」，
               不拿成本当亏损分下去 -->
          <template v-if="card.dividends?.length">
            <h4 class="pcr-sec-title sec-gap">{{ t('card.dividends') }}</h4>
            <div v-for="d in card.dividends" :key="d.contributor" class="settle-row">
              <span>{{ d.contributor }} <i class="pcr-dim">{{ d.share_pct }}%</i></span>
              <b class="pcr-mono" :class="profitClass(d.dividend_cny)">{{ cny(d.dividend_cny) }}</b>
            </div>
          </template>
        </div>
      </div>

      <!-- ── 出售：左边填卖价，右边对着结算看 ─────────────────────────── -->
      <div v-else-if="active === 'sale'" class="split">
        <el-form label-position="top" class="pcr-form split-main" @submit.prevent>
          <el-form-item :label="t('card.saleDate')">
            <el-date-picker v-model="form.sale_date" type="date" value-format="YYYY-MM-DD" :editable="!isTouch" />
          </el-form-item>
          <el-form-item :label="t('card.saleFx')">
            <div class="pcr-ro">
              <span class="pcr-mono">{{ card.sale_fx_rate ? formatRate(card.sale_fx_rate) : '—' }}</span>
              <span v-if="card.sale_fx_date" class="pcr-dim">· {{ card.sale_fx_date }}</span>
            </div>
          </el-form-item>
          <el-form-item :label="t('card.saleAmount')">
            <MoneyInput v-model:amount="form.sale_amount" v-model:currency="form.sale_currency" />
          </el-form-item>
          <el-form-item :label="t('card.domesticShipping')">
            <MoneyInput v-model:amount="form.domestic_shipping_amount" v-model:currency="form.domestic_shipping_currency" />
          </el-form-item>
        </el-form>

        <!-- 结算：成本拆成三项摊开，确认运费确实算进去了，而不是只看到一个总数 -->
        <aside class="settle split-side">
          <h4 class="pcr-sec-title">{{ t('detail.settlement') }}</h4>
          <div class="settle-row"><span>{{ t('card.purchaseAmount') }}</span><b class="pcr-mono">{{ cny(card.money.purchase_cny) }}</b></div>
          <div class="settle-row"><span>{{ t('card.intlShipping') }}</span><b class="pcr-mono">{{ cny(card.money.intl_shipping_cny) }}</b></div>
          <div class="settle-row"><span>{{ t('card.domesticShipping') }}</span><b class="pcr-mono">{{ cny(card.money.domestic_shipping_cny) }}</b></div>
          <div class="settle-row settle-sum"><span>{{ t('card.cost') }}</span><b class="pcr-mono">{{ cny(card.money.cost_total_cny) }}</b></div>
          <div class="settle-row"><span>{{ t('card.revenue') }}</span><b class="pcr-mono">{{ cny(card.money.sale_cny) }}</b></div>
          <div class="settle-row settle-big">
            <span>{{ t('card.profit') }}</span>
            <b class="pcr-mono" :class="profitClass(card.money.profit_cny)">{{ cny(card.money.profit_cny) }}</b>
          </div>
          <el-alert v-if="card.money.incomplete" :title="t('card.incomplete')" type="warning" :closable="false" show-icon class="mt" />
        </aside>
      </div>

      <!-- ── 图片 ──────────────────────────────────────────────────── -->
      <MediaManager v-else-if="active === 'media'" :card-id="card.id" :hosting-configured="hostingConfigured"
        @changed="onMediaChanged" />

      <!-- ── 记录 ──────────────────────────────────────────────────── -->
      <template v-else-if="active === 'log'">
        <StatusTimeline v-if="card.status_logs?.length" :logs="card.status_logs" />
        <el-empty v-else :description="t('detail.noLogs')" :image-size="60" />
      </template>
    </template>
  </DetailShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Clock, Document, Picture, Sell, ShoppingCart, WarningFilled } from '@element-plus/icons-vue'
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

// 当前模块。打开时总是从「基本信息」开始：这是认货的那一页，其余几页都是在它之后才去看的
const active = ref('basic')
// 图片数单独记：导航角标要它，而 card 快照只在保存时才刷新，传图不触发保存
const mediaCount = ref(0)
const modules = computed(() => [
  { key: 'basic', label: t('detail.modBasic'), icon: Document },
  { key: 'purchase', label: t('detail.modPurchase'), icon: ShoppingCart, badge: card.value?.fund_draws?.length || 0 },
  { key: 'sale', label: t('detail.modSale'), icon: Sell },
  { key: 'media', label: t('detail.modMedia'), icon: Picture, badge: mediaCount.value },
  { key: 'log', label: t('detail.modLog'), icon: Clock }
])
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
/* 骨架（顶栏 / 摘要条 / 导航 / 模块区）在 DetailShell 里；表单网格 .pcr-form 在 App.vue */
.head-cover {
  flex: none;
  width: 52px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  background: #0e1830;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #3a4a66;
  font-size: 18px;
}
.head-cover img { width: 100%; height: 100%; object-fit: cover; }
.head-text { min-width: 0; }
.head-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.head-name { margin: 0; font-size: 18px; color: #e6edf7; }
.head-sub { font-size: 12px; margin-top: 2px; }

.sum-item { display: flex; align-items: baseline; gap: 8px; }
.sum-label { font-size: 12px; color: #8a94a6; }
.sum-item b { font-size: 15px; color: #e6edf7; }
.sum-item .sum-big { font-size: 18px; }
.sum-sub { font-size: 12px; }
.sum-flag { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: #e6a23c; }

/* 模块内左右分栏：左边填、右边对照（出售 ↔ 结算、出资 ↔ 分摊） */
.split { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 24px; align-items: start; }
.split-main { min-width: 0; }
.split-side { min-width: 0; }
.sec-gap { margin-top: 22px; }
.small { font-size: 12px; margin: 8px 0 0; }

.settle {
  padding: 14px 16px;
  border: 1px solid var(--pcr-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}
.settle-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 13px; }
.settle-row span { color: #8a94a6; }
.settle-row b { color: #e6edf7; font-size: 14px; }
.settle-sum { border-top: 1px dashed var(--pcr-border); margin-top: 4px; padding-top: 10px; }
.settle-big b { font-size: 20px; }
.mt { margin-top: 10px; }

/* 序列号 30 位字母数字要完整看得见、0 和 O 分得清 */
.mono-input :deep(.el-input__inner) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
.url-open { color: #8fb8ff; text-decoration: none; padding: 0 4px; }
.hint {
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.7;
  border-radius: 6px;
}
.hint.warn { color: #e6a23c; background: rgba(230, 162, 60, 0.08); }

.pool-draw { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pool-done { color: #4ade80; font-size: 13px; }
.pool-warn { color: #e6a23c; font-size: 12px; }

/* 触屏：small 按钮只有指甲盖大 */
@media (hover: none) {
  .pool-draw :deep(.el-button) { min-height: 34px; padding: 8px 14px; }
}

@media (max-width: 768px) {
  /* 手机上一律 16px：iOS 聚焦更小的输入框会强行放大整页且不复位（同 App.vue 那条），
     scoped 的 :deep 特异度更高，得在这里自己写一遍 */
  .mono-input :deep(.el-input__inner) { font-size: 16px; }
  .head-name { font-size: 16px; }
  .split { grid-template-columns: minmax(0, 1fr); }
  .sum-item .sum-big { font-size: 16px; }
}
</style>
