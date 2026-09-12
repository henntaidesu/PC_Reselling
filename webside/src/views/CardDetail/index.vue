<template>
  <div class="detail" v-loading="loading">
    <div class="detail-head">
      <el-button :icon="ArrowLeft" text @click="$router.back()">{{ t('common.close') }}</el-button>
      <div v-if="card" class="head-right">
        <AutoSaveBadge :saving="autosave.saving.value" :saved-once="autosave.savedOnce.value" />
      </div>
    </div>

    <template v-if="card">
      <!-- 标题行只做展示，跟着下面的字段实时变：一行里塞三个输入框反而看不出这是哪张卡 -->
      <div class="title-row">
        <span class="pcr-mono mgmt">{{ card.mgmt_no }}</span>
        <h2 class="model">{{ [form.brand, form.model].filter(Boolean).join(' ') || t('card.noModel') }}</h2>
        <span v-if="form.core_no" class="core-badge">{{ form.core_no }}</span>
        <StatusTag :status="form.status" />
        <el-tag v-if="card.is_draft" size="small" type="warning" effect="plain">{{ t('common.draft') }}</el-tag>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <!-- 关键信息。每一行的值都是直接可改的控件，没有「编辑」这个模式 -->
          <el-card shadow="never" class="info-card">
            <template #header>{{ t('card.purchaseInfo') }} / {{ t('card.saleInfo') }}</template>

            <InlineField :label="t('card.brand')">
              <el-select v-model="form.brand" filterable allow-create default-first-option clearable>
                <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.name" />
              </el-select>
            </InlineField>
            <InlineField :label="t('card.model')">
              <el-select v-model="form.model" filterable allow-create default-first-option clearable>
                <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.name" />
              </el-select>
            </InlineField>
            <InlineField :label="t('card.coreNo')">
              <el-input v-model="form.core_no" />
            </InlineField>
            <InlineField :label="t('card.status')">
              <StatusSelect v-model="form.status" />
            </InlineField>

            <el-divider />

            <InlineField :label="t('card.serialNo')">
              <el-input v-model="form.serial_no" class="mono-input" />
            </InlineField>
            <InlineField :label="t('card.platform')">
              <el-select v-model="form.source_platform" clearable>
                <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </InlineField>
            <InlineField :label="t('card.seller')">
              <el-input v-model="form.seller" />
            </InlineField>
            <InlineField :label="t('card.orderNo')">
              <el-input v-model="form.order_no" />
            </InlineField>
            <InlineField :label="t('card.itemUrl')">
              <el-input v-model="form.item_url" />
              <a v-if="form.item_url" :href="form.item_url" target="_blank" class="row-link"
                :title="t('common.detail')">↗</a>
            </InlineField>

            <el-divider />

            <InlineField :label="t('card.purchaseDate')">
              <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" />
            </InlineField>
            <InlineField :label="t('card.purchaseAmount')">
              <MoneyInput v-model:amount="form.purchase_amount" v-model:currency="form.purchase_currency" />
            </InlineField>
            <InlineField :label="t('card.intlShipping')">
              <MoneyInput v-model:amount="form.intl_shipping_amount" v-model:currency="form.intl_shipping_currency" />
            </InlineField>
            <!-- 汇率是按日期取的快照，不给手改：改了日期，保存之后这一行自己就变了 -->
            <InlineField :label="t('card.purchaseFx')" readonly>
              <span class="pcr-mono">{{ card.purchase_fx_rate ? formatRate(card.purchase_fx_rate) : '—' }}<span
                v-if="card.purchase_fx_date" class="pcr-dim"> · {{ card.purchase_fx_date }}</span></span>
            </InlineField>
            <InlineField :label="t('card.fundSource')">
              <el-select v-model="form.fund_source">
                <el-option :label="t('card.fundOwn')" value="own" />
                <el-option :label="t('card.fundPool')" value="pool" />
              </el-select>
            </InlineField>
            <!-- 池子要点了这里才真的少钱。详情页是边填边自动保存的，没有这道闸门，
                 购入价刚敲了两位数就已经从池里扣走一笔了 -->
            <InlineField v-if="usePool" :label="t('card.poolDraw')" readonly>
              <div class="pool-draw">
                <template v-if="poolDrawn">
                  <span class="pool-done">{{ t('card.poolDrawn') }}</span>
                  <el-button link size="small" :loading="poolBusy" @click="cancelPoolDraw">
                    {{ t('card.poolUndo') }}
                  </el-button>
                </template>
                <el-button v-else type="primary" size="small" :loading="poolBusy"
                  :disabled="poolCurrencyMismatch" @click="confirmPoolDraw">
                  {{ t('card.poolConfirm') }}
                </el-button>
                <span v-if="poolCurrencyMismatch" class="pool-warn">{{ t('card.poolCurrencyWarn') }}</span>
              </div>
            </InlineField>

            <el-divider />

            <InlineField :label="t('card.saleDate')">
              <el-date-picker v-model="form.sale_date" type="date" value-format="YYYY-MM-DD" />
            </InlineField>
            <InlineField :label="t('card.saleAmount')">
              <MoneyInput v-model:amount="form.sale_amount" v-model:currency="form.sale_currency" />
            </InlineField>
            <InlineField :label="t('card.domesticShipping')">
              <MoneyInput v-model:amount="form.domestic_shipping_amount"
                v-model:currency="form.domestic_shipping_currency" />
            </InlineField>
            <InlineField :label="t('card.saleFx')" readonly>
              <span class="pcr-mono">{{ card.sale_fx_rate ? formatRate(card.sale_fx_rate) : '—' }}<span
                v-if="card.sale_fx_date" class="pcr-dim"> · {{ card.sale_fx_date }}</span></span>
            </InlineField>

            <el-divider />

            <InlineField :label="t('card.note')" stack>
              <el-input v-model="form.note" type="textarea" :rows="2" />
            </InlineField>

            <!-- 汇率取自哪一天、有没有回退过，都在这里说清楚；空着就是一切正常 -->
            <div v-if="card.warnings?.length" class="hint warn">
              <div v-for="(w, i) in card.warnings" :key="i">{{ w }}</div>
            </div>
          </el-card>

          <!-- 利润卡：算出来的数，不可改 -->
          <el-card shadow="never" class="profit-card">
            <div class="profit-row"><span>{{ t('card.cost') }}</span><b class="pcr-mono">{{ cny(card.money.cost_total_cny) }}</b></div>
            <div class="profit-row"><span>{{ t('card.revenue') }}</span><b class="pcr-mono">{{ cny(card.money.sale_cny) }}</b></div>
            <div class="profit-row big">
              <span>{{ t('card.profit') }}</span>
              <b class="pcr-mono" :class="profitClass(card.money.profit_cny)">{{ cny(card.money.profit_cny) }}</b>
            </div>
            <div class="profit-row"><span>{{ t('card.margin') }}</span><b class="pcr-mono">{{ card.money.profit_margin === null ? '—' : card.money.profit_margin + '%' }}</b></div>
            <el-alert v-if="card.money.incomplete" :title="t('card.incomplete')" type="warning" :closable="false" show-icon class="mt" />
          </el-card>

          <PoolBreakdown v-if="card.fund_draws?.length" :draws="card.fund_draws" class="block" />
          <StatusTimeline v-if="card.status_logs?.length" :logs="card.status_logs" class="block" />
        </el-col>

        <el-col :xs="24" :lg="14">
          <el-card shadow="never">
            <template #header>{{ t('card.media') }}</template>
            <MediaManager :card-id="card.id" :hosting-configured="hostingConfigured" @changed="onMediaChanged" />
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
import { ArrowLeft } from '@element-plus/icons-vue'
import { cardsApi, optionsApi, systemApi } from '@/api'
import { cny, formatRate, profitClass } from '@/utils/format'
import { ElMessage } from '@/utils/notify'
import { useAutoSave } from '@/composables/useAutoSave'
import { usePlatforms } from '@/composables/usePlatforms'
import { useMetaStore } from '@/stores/meta'
import AutoSaveBadge from '@/components/AutoSaveBadge.vue'
import InlineField from '@/components/InlineField.vue'
import MediaManager from '@/components/MediaManager.vue'
import MoneyInput from '@/components/MoneyInput.vue'
import PoolBreakdown from '@/components/PoolBreakdown.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatusSelect from '@/components/StatusSelect.vue'
import StatusTimeline from '@/components/StatusTimeline.vue'

const { t } = useI18n()
const route = useRoute()
const meta = useMetaStore()

// card = 服务端快照（金额、汇率、分摊、时间线、草稿标记），form = 可编辑的那些列。
// 两者必须分开：保存的返回值要用来刷新展示部分，但绝不能回灌 form——用户在请求
// 往返的那几百毫秒里敲的字会被它覆盖掉。
const card = ref(null)
const loading = ref(false)
const hostingConfigured = ref(true)

const brands = computed(() => meta.brands)
const models = computed(() => meta.models)
const { platforms } = usePlatforms()

function blankForm() {
  return {
    id: null,
    brand: null, model: null, core_no: null, serial_no: null,
    source_platform: null, seller: null, item_url: null, order_no: null,
    purchase_date: null, purchase_amount: null, purchase_currency: 'JPY',
    intl_shipping_amount: null, intl_shipping_currency: 'JPY',
    domestic_shipping_amount: null, domestic_shipping_currency: 'CNY',
    sale_date: null, sale_amount: null, sale_currency: 'CNY',
    fund_source: 'own',
    status: 'purchased', note: null
    // 汇率一律按日期自动获取，不在这里填
  }
}
const form = reactive(blankForm())

const usePool = computed(() => form.fund_source === 'pool')
// 池子里是日元，人民币支付的部分与它无关：选了池子但币种是人民币时要说清楚
const poolCurrencyMismatch = computed(() =>
  usePool.value && form.purchase_currency !== 'JPY' && form.purchase_amount
)

// 走资金池 + 已确认扣除，才是池子真的少了钱的状态
const poolDrawn = computed(() => usePool.value && Boolean(card.value?.pool_confirmed_at))
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
  out.fund_source = row.fund_source || 'own'
  out.status = row.status || 'purchased'
  return out
}

async function load() {
  loading.value = true
  autosave.pause()
  try {
    const res = await cardsApi.get(route.params.id)
    card.value = res
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
  } catch { /* 字典写入失败不影响卡片本身 */ }
}

// 只传了图、一个字都没改的新卡：它这时还是草稿，离开页面会被当空卡删掉，刚传的图
// 跟着一起没。所以传完图立刻存一次，把它转正。
async function onMediaChanged() {
  if (card.value?.is_draft) {
    try { await doSave() } catch { /* 拦截器已提示 */ }
  }
}

// 离开前把没落盘的改动存完；仍是草稿（从「新增」进来又什么都没填）就把这张空卡删掉
onBeforeRouteLeave(async () => {
  autosave.pause()
  if (autosave.pending.value) await autosave.flush()
  if (card.value?.is_draft) {
    try { await cardsApi.remove(card.value.id, true) } catch { /* 删不掉就留给启动时的清理 */ }
  }
})

onMounted(async () => {
  await meta.ensure()
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
.core-badge { font-size: 12px; padding: 2px 8px; border-radius: 6px; background: #1b2942; color: #a6adb4; }
.info-card, .profit-card { margin-bottom: 16px; }
.block { margin-bottom: 16px; }
.info-card :deep(.el-divider) { margin: 10px 0; }
/* 序列号 30 位字母数字要完整看得见 */
.mono-input :deep(.el-input__inner) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
.row-link { color: #8fb8ff; text-decoration: none; flex: 0 0 auto; padding: 0 4px; }
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
.profit-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; }
.profit-row span { color: #8a94a6; }
.profit-row b { color: #e6edf7; font-size: 15px; }
.profit-row.big b { font-size: 22px; }
.mt { margin-top: 10px; }

/* 「确认扣除」那一行：按钮 + 已扣除标记，与旁边的 InlineField 对齐 */
.pool-draw { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pool-done { color: #4ade80; font-size: 13px; }
.pool-warn { color: #e6a23c; font-size: 12px; }
</style>
