<template>
  <div class="cards-page">
    <div class="page-head">
      <h2 class="page-title">{{ t('route.cards') }}</h2>
    </div>

    <!-- 统计模块：随下方筛选联动，覆盖整个筛选结果（不只当前页），显卡与整机合计。
         手机端不展示——8 张卡两列排下来要划掉大半屏才看得到表格。 -->
    <el-card v-if="!isMobile" class="stats-card" shadow="never">
      <div v-loading="statsLoading">
        <el-row :gutter="16" class="stat-row">
          <el-col v-for="card in statCards" :key="card.key" :xs="12" :sm="12" :md="8" :lg="6" :xl="3">
            <StatCard
              :label="card.label"
              :value="card.value"
              :sub="card.sub"
              :icon="card.icon"
              :color="card.color"
              :value-class="card.valueClass"
            />
          </el-col>
        </el-row>
        <div v-if="stats.incomplete" class="stats-warn">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ t('dashboard.incompleteWarn', { n: stats.incomplete }) }}</span>
        </div>
      </div>
    </el-card>

    <!-- 筛选行 -->
    <el-card class="filter-card" shadow="never">
      <div class="filters">
        <el-input
          v-model="filters.keyword"
          :placeholder="t('common.search')"
          clearable
          class="f-keyword"
          @keyup.enter="reload"
          @clear="reload"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filters.kind" :placeholder="t('inv.allKinds')" clearable class="f-kind" @change="reload">
          <el-option :label="t('inv.card')" value="card" />
          <el-option :label="t('inv.device')" value="device" />
        </el-select>
        <StatusSelect v-model="filters.status" multiple collapse-tags :placeholder="t('card.status')"
          clearable class="f-status" @change="reload" />
        <el-select v-model="filters.brand" :placeholder="t('card.brand')" clearable filterable class="f-brand" @change="reload">
          <el-option v-for="b in usedBrands" :key="b.brand" :label="`${b.brand} (${b.count})`" :value="b.brand" />
        </el-select>
        <el-select v-model="filters.source_platform" :placeholder="t('card.platform')" clearable class="f-platform" @change="reload">
          <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          :start-placeholder="t('card.purchaseDate')"
          :end-placeholder="t('card.purchaseDate')"
          class="f-date"
          @change="reload"
        />
        <el-button :icon="Refresh" @click="resetFilters">{{ t('common.reset') }}</el-button>
        <!-- 新增挨着重置放：这一行是「对这张表做点什么」的地方，按钮都聚在同一处，
             不用在标题栏和筛选行之间来回找 -->
        <el-button type="primary" :icon="Plus" @click="addVisible = true">{{ t('common.add') }}</el-button>
      </div>
    </el-card>

    <!-- 表格：显卡与整机同一张表，靠「类型」列区分。整机可展开看部件明细 -->
    <el-card class="table-card" shadow="never">
      <el-table
        v-loading="loading"
        :data="rows"
        class="cards-table"
        row-key="row_key"
        :tree-props="{ children: 'children' }"
        :row-class-name="rowClass"
        @row-click="onRowClick"
      >
        <el-table-column :label="t('card.cover')" width="110">
          <template #default="{ row }">
            <!-- 二级行（部件）没有封面，这一格留空——树形展开的箭头和缩进由 el-table
                 画在第一列里，所以这一列要比原来宽一点 -->
            <div v-if="row.kind !== 'part'" class="cover">
              <img v-if="cover(row)" :src="cover(row)" alt="" loading="lazy" />
              <el-icon v-else class="cover-empty">
                <component :is="row.kind === 'device' ? 'Monitor' : 'Picture'" />
              </el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('inv.kind')" width="90">
          <template #default="{ row }">
            <!-- 顶层行显示显卡 / 整机，二级行显示这个部件是什么（CPU / 内存…） -->
            <el-tag size="small" effect="plain" :type="kindTagType(row)">
              {{ row.kind === 'part' ? t('partType.' + row.part_type) : t('inv.' + row.kind) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('inv.name')" min-width="190">
          <template #default="{ row }">
            <div class="model-cell">
              <span class="model-name">{{ nameOf(row) }}</span>
              <span v-if="row.mgmt_no || row.subtitle" class="pcr-dim sub">
                <span class="pcr-mono">{{ row.mgmt_no }}</span>
                <template v-if="row.subtitle"> · {{ row.subtitle }}</template>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('card.status')" width="110">
          <template #default="{ row }">
            <!-- 没卖出去的部件谈不上「已购入 / 已打款」这些流转状态，标成未出售更准 -->
            <StatusTag v-if="row.kind !== 'part' || row.sold" :status="row.status" />
            <el-tag v-else size="small" type="info" effect="plain">{{ t('device.unsold') }}</el-tag>
          </template>
        </el-table-column>
        <!-- 日期没有就空着，不画「—」：这两列里空白本身就是「还没到那一步」，
             一列破折号只是噪音。金额列的「—」不一样，那是「缺汇率算不出来」，得留着。 -->
        <el-table-column :label="t('card.purchaseDate')" width="120">
          <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.purchase_date }}</span></template>
        </el-table-column>
        <el-table-column :label="t('card.saleDate')" width="120">
          <template #default="{ row }">
            <!-- 整机这一格空着：部件是分批卖的，「最后成交那天」既不是这台机器卖完的
                 日子，也对不上任何一件的成交日，摆在顶层行上只会被当成前者。逐件的
                 出售日期在展开后的二级行上，那才是实情。 -->
            <span v-if="row.kind !== 'device'" class="pcr-mono pcr-dim">{{ row.sale_date }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('device.partsCount')" width="96" align="center">
          <template #default="{ row }">
            <!-- 显卡就是一件，部件行本身也不再分件，只有整机这一格有意义 -->
            <span v-if="row.kind === 'device'" class="pcr-mono">{{ row.sold_count }} / {{ row.part_count }}</span>
            <span v-else class="pcr-dim">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('card.cost')" width="140" align="right">
          <template #default="{ row }">
            <!-- 部件没有单件成本：整机是一口价买的，总价不往部件上摊 -->
            <el-tooltip v-if="row.kind === 'part'" :content="t('device.noPartCost')">
              <span class="pcr-dim">—</span>
            </el-tooltip>
            <template v-else>
              <!-- 总成本 = 购入价 + 国际运费 + 国内运费。三项都已计入合计，悬浮摊开是
                   为了让人一眼确认运费确实算进去了，而不是只看到一个总数在那儿。 -->
              <el-tooltip placement="left">
                <template #content>
                  <div class="cost-tip">
                    <div><span>{{ t('card.purchaseAmount') }}</span><b>{{ cny(row.purchase_cny) }}</b></div>
                    <div><span>{{ t('card.intlShipping') }}</span><b>{{ cny(row.intl_shipping_cny) }}</b></div>
                    <div><span>{{ t('card.domesticShipping') }}</span><b>{{ cny(row.domestic_shipping_cny) }}</b></div>
                    <div class="cost-tip-sum"><span>{{ t('card.cost') }}</span><b>{{ cny(row.cost_total_cny) }}</b></div>
                  </div>
                </template>
                <span class="pcr-mono cost-value">{{ cny(row.cost_total_cny) }}</span>
              </el-tooltip>
              <!-- 这笔成本的钱从哪儿出的，用一个字标在金额后面：
                   「池」= 按资金池的注资汇率折的，不是买入当天的牌价（不标出来对不上账）；
                   「自」= 自有资金，按购入日牌价折。两者都标才有意义——只标「池」的话，
                   没有标记的行到底是自有资金，还是选了池子但还没点「确认扣除」，看不出来。
                   后一种两个标都不给，它的成本此刻仍按牌价算。 -->
              <el-tooltip v-if="row.from_pool" :content="t('card.poolDrawn')">
                <el-tag size="small" type="primary" effect="plain" class="pool-tag">{{ t('card.poolTag') }}</el-tag>
              </el-tooltip>
              <el-tooltip v-else-if="row.fund_source === 'own'" :content="t('card.fundOwn')">
                <el-tag size="small" type="info" effect="plain" class="pool-tag">{{ t('card.ownTag') }}</el-tag>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <!-- 日元成本单独一列，挨着人民币那列：货是在日本买的，对着日站的成交价复核时
             看日元才顺手。两列是同一笔账的两种说法（见 cards._to_jpy），不是两套口径——
             所以不再重复悬浮明细，明细挂在左边那一列上。 -->
        <el-table-column :label="t('inv.costJpy')" width="130" align="right">
          <template #default="{ row }">
            <span class="pcr-mono" :class="{ 'pcr-dim': row.cost_total_jpy === null }">
              {{ jpy(row.cost_total_jpy) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('device.revenue')" width="130" align="right">
          <template #default="{ row }">
            <span class="pcr-mono">{{ cny(row.sale_cny) }}</span>
            <!-- 部件的净收入（扣掉国内运费）标在下面，「已收回」本身仍是售价，
                 二级行加起来才等于整机那一行 -->
            <div v-if="row.kind === 'part' && row.domestic_shipping_cny" class="pcr-dim sub pcr-mono">
              {{ t('device.netIncome') }} {{ cny(row.net_cny) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('card.profit')" width="150" align="right">
          <template #header>
            <!-- 这一列是净利润：收入减掉的成本里含国际运费与国内运费。表头标一下，
                 免得被当成「售价 − 购入价」的毛利去对账。 -->
            <el-tooltip :content="t('card.netProfitHint')">
              <span class="net-profit-head">{{ t('card.profit') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip v-if="row.kind === 'part'" :content="t('device.noPartCost')">
              <span class="pcr-dim">—</span>
            </el-tooltip>
            <template v-else>
              <span class="pcr-mono" :class="profitClass(row.profit_cny)">{{ cny(row.profit_cny) }}</span>
              <el-tooltip v-if="row.incomplete" :content="t('card.incomplete')">
                <el-icon class="warn-icon"><WarningFilled /></el-icon>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="fetch"
          @size-change="fetch"
        />
      </div>
    </el-card>

    <!-- 新增什么：显卡还是整机。两者的录入方式根本不同（一进一出 vs 一笔买进、拆成
         部件分别卖），选错了只能删掉重来，所以这里摆两张把区别说清楚的卡片，
         而不是下拉菜单里两行长得一样的字。 -->
    <el-dialog v-model="addVisible" :title="t('inv.addPick')" width="520px" align-center>
      <div class="add-picker">
        <button
          v-for="opt in ADD_OPTIONS"
          :key="opt.kind"
          class="add-option"
          type="button"
          :disabled="adding"
          :style="{ '--opt-color': opt.color }"
          @click="onAdd(opt.kind)"
        >
          <el-icon class="add-option-icon"><component :is="opt.icon" /></el-icon>
          <span class="add-option-title">{{ t(opt.label) }}</span>
          <span class="add-option-desc">{{ t(opt.desc) }}</span>
        </button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onActivated, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Cpu, Monitor, Plus, Refresh, Search, WarningFilled
} from '@element-plus/icons-vue'
import { cardsApi, devicesApi, inventoryApi, optionsApi } from '@/api'
import { cny, firstImage, jpy, profitClass } from '@/utils/format'
import { ElMessage } from '@/utils/notify'
import { useIsMobile } from '@/composables/useIsMobile'
import { usePlatforms } from '@/composables/usePlatforms'
import { useMetaStore } from '@/stores/meta'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatusSelect from '@/components/StatusSelect.vue'

defineOptions({ name: 'Cards' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const meta = useMetaStore()
const { isMobile } = useIsMobile()

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const usedBrands = ref([])

const filters = reactive({ keyword: '', kind: null, status: [], brand: null, source_platform: null })
// 购入日期区间：绑定 daterange 选择器，拆成 purchase_from/purchase_to 传后端
const dateRange = ref(null)

const emptyStats = () => ({
  total: 0, cards: 0, devices: 0, in_stock: 0, settled: 0,
  total_cost_cny: 0, total_cost_jpy: 0, total_revenue_cny: 0, total_profit_cny: 0,
  recovery: null, incomplete: 0
})
const stats = ref(emptyStats())
const statsLoading = ref(false)

const { platforms } = usePlatforms()

// 顶部统计卡。顺序固定：先数量、后金额，颜色跟着指标走，不随数值变化重排
const statCards = computed(() => {
  const s = stats.value
  const profit = s.total_profit_cny
  return [
    { key: 'total', label: t('inv.total'), value: s.total, icon: 'Box', color: '#409EFF' },
    { key: 'cards', label: t('inv.cards'), value: s.cards, icon: 'Cpu', color: '#5b8cff' },
    { key: 'devices', label: t('inv.devices'), value: s.devices, icon: 'Monitor', color: '#E6A23C' },
    { key: 'inStock', label: t('dashboard.inStock'), value: s.in_stock, icon: 'Goods', color: '#a78bfa' },
    { key: 'settled', label: t('inv.settled'), value: s.settled, icon: 'Sell', color: '#67C23A' },
    {
      key: 'cost',
      label: t('dashboard.totalCost'),
      value: cny(s.total_cost_cny),
      // 与列表里每一行同样的处理：日元是参考口径，压在主数字下面
      sub: jpy(s.total_cost_jpy),
      icon: 'Coin',
      color: '#F56C6C'
    },
    { key: 'revenue', label: t('dashboard.totalRevenue'), value: cny(s.total_revenue_cny), icon: 'Money', color: '#38bdf8' },
    {
      key: 'profit',
      label: t('dashboard.totalProfit'),
      value: cny(profit),
      icon: 'TrendCharts',
      color: profit > 0 ? '#67C23A' : profit < 0 ? '#F56C6C' : '#409EFF',
      valueClass: profitClass(profit)
    }
  ]
})

// 二级行（部件）整行淡一档，一眼能看出层级
const rowClass = ({ row }) => (row.kind === 'part' ? 'part-row' : '')
const kindTagType = (row) => (row.kind === 'device' ? 'warning' : row.kind === 'part' ? 'info' : 'primary')

function cover(row) {
  const img = firstImage(row.media)
  if (!img || img.kind !== 'image') return null
  return img.public_url + (img.public_url.includes('?') ? '&' : '?') + 'w=200'
}
function nameOf(row) {
  if (row.title) return row.title
  if (row.kind === 'device') return t('device.noTitle')
  if (row.kind === 'part') return t('partType.' + row.part_type)
  return t('card.noModel')
}

// 列表和统计共用的筛选参数
function filterParams() {
  return {
    keyword: filters.keyword || undefined,
    kind: filters.kind || undefined,
    status: filters.status.length ? filters.status.join(',') : undefined,
    brand: filters.brand || undefined,
    source_platform: filters.source_platform || undefined,
    purchase_from: dateRange.value?.[0] || undefined,
    purchase_to: dateRange.value?.[1] || undefined
  }
}

async function fetch() {
  loading.value = true
  try {
    const res = await inventoryApi.list({ ...filterParams(), page: page.value, page_size: pageSize.value })
    // 请求成功但形状不对，几乎只有一种原因：拿到的根本不是这个接口的响应（后端没重启、
    // 接口不存在时曾经会回一整页 HTML）。必须显式报出来——退化成一张「暂无数据」的空表
    // 是最难查的那种失败：页面看着好好的，数据却凭空消失了。
    if (!res || !Array.isArray(res.items) || typeof res.total !== 'number') {
      rows.value = []
      total.value = 0
      ElMessage.error(t('common.badResponse'))
      return
    }
    rows.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
  fetchStats()
}

async function fetchStats() {
  statsLoading.value = true
  try {
    const res = await inventoryApi.stats(filterParams())
    // 同上：形状不对就退回全 0，而不是把一个字段全是 undefined 的东西摆上去
    // ——那样每个指标都显示成「—」，看着像「没数据」，其实是响应根本不对。
    stats.value = typeof res?.total === 'number' ? res : emptyStats()
  } catch {
    stats.value = emptyStats()
  } finally {
    statsLoading.value = false
  }
}

function reload() {
  page.value = 1
  fetch()
}
function resetFilters() {
  filters.keyword = ''
  filters.kind = null
  filters.status = []
  filters.brand = null
  filters.source_platform = null
  dateRange.value = null
  reload()
}

async function loadAux() {
  await meta.ensure()
  const ub = await optionsApi.usedBrands()
  usedBrands.value = ub.items || []
}

// 新增 = 先建一行空草稿，再进详情页填。详情页本身就是编辑界面，没有第二套「新增
// 表单」要维护；草稿不进列表也不进统计，什么都没填就离开的话详情页会把它删掉。
// 新增弹窗的两张卡片。图标与颜色跟顶部统计卡里的「显卡」「整机」一致——
// 同一个东西在一个页面里换个地方就换套长相，只会让人多认一遍。
const ADD_OPTIONS = [
  { kind: 'card', icon: Cpu, color: '#5b8cff', label: 'inv.addCard', desc: 'inv.addCardDesc' },
  { kind: 'device', icon: Monitor, color: '#E6A23C', label: 'inv.addDevice', desc: 'inv.addDeviceDesc' }
]

const addVisible = ref(false)
const adding = ref(false)

// 建一行空草稿再跳进详情页（见 CLAUDE.md 的「草稿行」）。建的过程中把两张卡片禁掉：
// 手快点两下会建出两行草稿，其中一行没人管，只能等两小时后被清理掉。
async function onAdd(kind) {
  if (adding.value) return
  adding.value = true
  try {
    const draft = kind === 'device' ? await devicesApi.createDraft() : await cardsApi.createDraft()
    addVisible.value = false
    router.push(`/${kind === 'device' ? 'devices' : 'cards'}/${draft.id}`)
  } catch { /* 拦截器已提示 */ } finally {
    adding.value = false
  }
}

// 点一行就进它的详情页——看和改都在那里。部件行进的是它所属的那台整机：部件是整机
// 的一部分，没有自己的详情页。
function onRowClick(row) {
  if (row.kind === 'part') return router.push(`/devices/${row.device_id}`)
  router.push(`/${row.kind === 'device' ? 'devices' : 'cards'}/${row.id}`)
}

// 概览页点进来时带 ?status=xxx，直接把筛选摆好；带空的 status= 表示「看全部」。
// 判断的是「有没有这个参数」而不是它真不真：从详情页返回时 query 是空的，
// 那种情况下必须原样保留用户自己设的筛选，不能顺手清掉。
function applyRouteQuery() {
  if (!('status' in route.query)) return
  const status = route.query.status
  filters.status = String(status || '').split(',').filter(Boolean)
  page.value = 1
}

onActivated(() => {
  applyRouteQuery()
  loadAux()
  fetch()
})
</script>

<style scoped>
.pool-tag { margin-left: 5px; transform: scale(0.85); }
/* 成本上有明细可看：加条虚下划线提示可以悬浮，否则没人会想到把鼠标停上去 */
.cost-value { border-bottom: 1px dotted #5a6478; cursor: help; }
.net-profit-head { border-bottom: 1px dotted #5a6478; cursor: help; }
.cost-tip div { display: flex; justify-content: space-between; gap: 18px; line-height: 1.9; }
.cost-tip b { font-variant-numeric: tabular-nums; }
.cost-tip-sum { border-top: 1px solid rgba(255, 255, 255, 0.2); margin-top: 4px; padding-top: 4px; }
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title { font-size: 20px; }

/* 顶部统计卡（与 FreeMarket_Manager 库存页同一套版式） */
.stats-card { margin-bottom: 16px; border-radius: 8px; }
/* 换行后两排卡片之间的空隙由 el-col 的下边距给出；最后一排多出来的那 16px
   用行的负下边距抵掉，否则卡片和卡片底之间会比左右留白宽一截 */
.stat-row { margin-bottom: -16px; }
.stat-row :deep(.el-col) { margin-bottom: 16px; }
.stats-warn {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  font-size: 12px;
  color: #f5a623;
}

.filter-card { margin-bottom: 16px; }
.filter-card :deep(.el-card__body) { padding: 14px 16px; }
.filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.f-keyword { width: 210px !important; }
.f-kind { width: 120px !important; }
.f-status { width: 190px !important; }
.f-brand { width: 150px !important; }
.f-platform { width: 140px !important; }
.f-date { width: 250px !important; }

.cards-table :deep(.el-table__row) { cursor: pointer; }
/* 二级行（部件）压暗一档并留出缩进，和顶层行分得开 */
.cards-table :deep(.part-row) { background: rgba(91, 140, 255, 0.03); }
.cards-table :deep(.part-row .cell) { color: #b9c4d6; }
/* 树形展开箭头是 el-table 画在第一列单元格里的行内元素，而封面是个块级盒子——
   不排成一行的话，箭头会被顶到封面上面去。占位符和箭头统一宽度，让有子行和没子行
   的封面左边缘对齐。 */
.cards-table :deep(td.el-table__cell:first-child .cell) {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cards-table :deep(td.el-table__cell:first-child .cell > *) { flex: none; }
.cards-table :deep(td.el-table__cell:first-child .el-table__expand-icon),
.cards-table :deep(td.el-table__cell:first-child .el-table__placeholder) { width: 22px; }
.cover {
  width: 54px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  background: #0e1830;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover img { width: 100%; height: 100%; object-fit: cover; }
.cover-empty { color: #3a4a66; font-size: 18px; }
.model-cell { display: flex; flex-direction: column; }
.model-name { color: #e6edf7; }
.sub { font-size: 12px; }
.warn-icon { color: #f5a623; margin-left: 4px; vertical-align: middle; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }

/* ── 新增弹窗里的两张卡片 ──────────────────────────────────────────────
   用原生 button 而不是 div：键盘能 Tab 到、能回车按下、禁用态是浏览器原生的，
   这些在 div 上都得自己补一遍。 */
.add-picker { display: flex; gap: 12px; }
.add-option {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 18px 16px;
  border: 1px solid var(--pcr-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--pcr-text);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}
.add-option:hover:not(:disabled),
.add-option:focus-visible {
  /* 边框与图标本来就是这一类的代表色，悬浮时把边框点亮即可，不另配一套高亮色 */
  border-color: var(--opt-color);
  background: rgba(255, 255, 255, 0.05);
  outline: none;
}
.add-option:disabled { opacity: 0.6; cursor: default; }
.add-option-icon { font-size: 24px; color: var(--opt-color); }
.add-option-title { font-size: 15px; font-weight: 600; }
.add-option-desc { font-size: 12px; line-height: 1.5; color: var(--pcr-text-dim); }

@media (max-width: 768px) {
  .f-keyword, .f-kind, .f-status, .f-brand, .f-platform, .f-date { width: 100% !important; }
  .filters { flex-direction: column; align-items: stretch; }
  /* 两张卡片并排在手机上只剩半屏宽，说明文字会碎成每行两三个字 */
  .add-picker { flex-direction: column; }
}
</style>
