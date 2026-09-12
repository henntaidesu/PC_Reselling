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
        <!-- 手机上六个筛选器竖着排完要占掉大半屏，进页面第一眼看到的是一列空下拉框而
             不是货。所以窄屏默认只留搜索框，其余收进这个开关；按钮上的角标写着当前有
             几项在生效——收起来之后唯一的风险就是「明明有货却一条都不显示」而看不出
             是筛掉的。 -->
        <el-button v-if="isMobile" class="f-toggle" :icon="Filter" @click="filtersOpen = !filtersOpen">
          {{ t('common.filter') }}<span v-if="activeFilterCount" class="f-count">{{ activeFilterCount }}</span>
        </el-button>
        <template v-if="!isMobile || filtersOpen">
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
          <!-- 区间选择器在手机上摆不下：Element 的 daterange 面板是并排两个月历，
               写死 646px 宽（单个月历是 322px），360px 的屏上会被裁掉大半，右边那个月
               连同「确定」一起看不见。窄屏拆成起 / 止两个单日期选择器——面板只剩一个月，
               正好放得下，顺带也支持只填一头（后端两端本来就是各自独立判断的）。 -->
          <el-date-picker
            v-if="!isMobile"
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            :start-placeholder="t('card.purchaseDate')"
            :end-placeholder="t('card.purchaseDate')"
            class="f-date"
            @change="reload"
          />
          <template v-else>
            <el-date-picker
              :model-value="dateRange?.[0] || null"
              type="date"
              value-format="YYYY-MM-DD"
              :placeholder="t('inv.dateFrom')"
              class="f-date"
              @update:model-value="(v) => setRangeEnd(0, v)"
            />
            <el-date-picker
              :model-value="dateRange?.[1] || null"
              type="date"
              value-format="YYYY-MM-DD"
              :placeholder="t('inv.dateTo')"
              class="f-date"
              @update:model-value="(v) => setRangeEnd(1, v)"
            />
          </template>
          <el-button :icon="Refresh" @click="resetFilters">{{ t('common.reset') }}</el-button>
        </template>
        <!-- 新增挨着重置放：这一行是「对这张表做点什么」的地方，按钮都聚在同一处，
             不用在标题栏和筛选行之间来回找 -->
        <el-button type="primary" :icon="Plus" class="f-add" @click="addVisible = true">{{ t('common.add') }}</el-button>
      </div>
    </el-card>

    <!-- 表格：显卡与整机同一张表，靠「类型」列区分。整机可展开看部件明细 -->
    <el-card class="table-card" shadow="never">
      <!-- 手机改用卡片列表。这张表十一列合计约 1400px，在 360px 的屏上要横着划近四屏，
           而「哪一张卡、卖了没、赚没赚」这三件事分散在第三、第四和最后一列——横向滚动
           的表格永远没法让它们同时在眼前。所以窄屏换一种排法：同一批 rows、同一个
           onRowClick，只是把一行摊成一张卡。
           这不是第二套列表——取数、筛选、分页仍然只有上面那一份，这里不持有任何状态。 -->
      <div v-if="isMobile" v-loading="loading" class="m-list">
        <div v-for="row in rows" :key="row.row_key" class="m-card" @click="onRowClick(row)">
          <div class="m-top">
            <div class="cover m-cover">
              <img v-if="cover(row)" :src="cover(row)" alt="" loading="lazy" />
              <el-icon v-else class="cover-empty">
                <component :is="row.kind === 'device' ? 'Monitor' : 'Picture'" />
              </el-icon>
            </div>
            <div class="m-head">
              <div class="m-name">{{ nameOf(row) }}</div>
              <div v-if="row.mgmt_no || row.subtitle" class="sub pcr-dim">
                <span class="pcr-mono">{{ row.mgmt_no }}</span>
                <template v-if="row.subtitle"> · {{ row.subtitle }}</template>
              </div>
              <div class="m-tags">
                <el-tag size="small" effect="plain" :type="row.kind === 'device' ? 'warning' : 'primary'">
                  {{ t('inv.' + row.kind) }}
                </el-tag>
                <StatusTag :status="row.status" />
                <!-- 整机的「已售 / 总件数」：顶层行上最该先看到的就是它还剩几件没出手 -->
                <el-tag v-if="row.kind === 'device'" size="small" effect="plain" type="info" class="pcr-mono">
                  {{ row.sold_count }} / {{ row.part_count }}
                </el-tag>
              </div>
            </div>
          </div>

          <!-- 成本 / 收入 / 利润三个数并排。桌面端成本上挂着「购入 + 国际运费 + 国内运费」
               的悬浮明细，这里不复刻：触屏没有悬浮，改成点一下弹层就和「点整行进详情」
               抢同一次点击，而详情页里那三项本来就是分行列着的。 -->
          <div class="m-metrics">
            <div class="m-metric">
              <span class="m-label">{{ t('card.cost') }}</span>
              <b class="pcr-mono">{{ money(row.cost_total_cny) }}</b>
              <!-- 日元成本压在人民币下面。货是在日站买的，对着成交页复核时看的是这个数；
                   两者是同一笔账的两种说法，不是两套口径（见 cards._to_jpy） -->
              <span class="m-sub pcr-mono pcr-dim">{{ money(row.cost_total_jpy, jpy) }}</span>
            </div>
            <div class="m-metric">
              <span class="m-label">{{ t('device.revenue') }}</span>
              <b class="pcr-mono">{{ money(row.sale_cny) }}</b>
            </div>
            <div class="m-metric">
              <span class="m-label">{{ t('card.profit') }}</span>
              <b class="pcr-mono" :class="profitClass(row.profit_cny)">
                {{ money(row.profit_cny) }}
                <el-icon v-if="row.incomplete" class="warn-icon"><WarningFilled /></el-icon>
              </b>
            </div>
          </div>

          <div class="m-foot">
            <span class="pcr-mono pcr-dim">{{ row.purchase_date }}</span>
            <!-- 整机不显示成交日：部件是分批卖的，任何一个日期摆在顶层行上都会被当成
                 「这台机器卖完的那天」（与桌面端同一条理由） -->
            <span v-if="row.kind !== 'device' && row.sale_date" class="pcr-mono pcr-dim">→ {{ row.sale_date }}</span>
            <button v-if="row.children && row.children.length" class="m-expand" type="button"
              @click.stop="togglePartsOf(row)">
              {{ t('device.partsOverview') }}
              <el-icon><component :is="expandedKeys.has(row.row_key) ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
            </button>
          </div>

          <div v-if="row.children && row.children.length && expandedKeys.has(row.row_key)" class="m-parts">
            <div v-for="part in row.children" :key="part.row_key" class="m-part">
              <PartTypeTag :type="part.part_type" />
              <span class="m-part-name">{{ nameOf(part) }}</span>
              <StatusTag v-if="part.sold" :status="part.status" />
              <el-tag v-else size="small" type="info" effect="plain">{{ t('device.unsold') }}</el-tag>
              <span class="pcr-mono m-part-money">{{ money(part.sale_cny) }}</span>
            </div>
          </div>
        </div>
        <el-empty v-if="!rows.length && !loading" :description="t('common.noData')" :image-size="70" />
      </div>

      <el-table
        v-else
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
            <!-- 顶层行显示显卡 / 整机，二级行显示这个部件是什么（CPU / 内存…）。
                 部件那一套颜色在 PartTypeTag 里，整机详情的部件表用的是同一个组件 -->
            <PartTypeTag v-if="row.kind === 'part'" :type="row.part_type" />
            <el-tag v-else size="small" effect="plain" :type="row.kind === 'device' ? 'warning' : 'primary'">
              {{ t('inv.' + row.kind) }}
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
        <!-- 没有就空着，不画「—」：这张表里空白只有一个意思——这一格本来就没有数据。
             整张表都按这条来（见下面的 money()），一列破折号只是噪音。 -->
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
            <!-- 只有整机这一格有意义：显卡就是一件，部件行本身也不再分件。
                 不适用就空着——「0 / 0」和「—」都会让人以为这里该有个数。 -->
            <span v-if="row.kind === 'device'" class="pcr-mono">{{ row.sold_count }} / {{ row.part_count }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('card.cost')" width="140" align="right">
          <template #default="{ row }">
            <!-- 部件这一格空着：没有单件成本（整机是一口价买的，总价不往部件上摊） -->
            <template v-if="row.kind !== 'part'">
              <!-- 总成本 = 购入价 + 国际运费 + 国内运费。三项都已计入合计，悬浮摊开是
                   为了让人一眼确认运费确实算进去了，而不是只看到一个总数在那儿。 -->
              <el-tooltip placement="left">
                <template #content>
                  <div class="cost-tip">
                    <div><span>{{ t('card.purchaseAmount') }}</span><b>{{ money(row.purchase_cny) }}</b></div>
                    <div><span>{{ t('card.intlShipping') }}</span><b>{{ money(row.intl_shipping_cny) }}</b></div>
                    <div><span>{{ t('card.domesticShipping') }}</span><b>{{ money(row.domestic_shipping_cny) }}</b></div>
                    <div class="cost-tip-sum"><span>{{ t('card.cost') }}</span><b>{{ money(row.cost_total_cny) }}</b></div>
                  </div>
                </template>
                <span class="pcr-mono cost-value">{{ money(row.cost_total_cny) }}</span>
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
            <span v-if="row.kind !== 'part'" class="pcr-mono">{{ money(row.cost_total_jpy, jpy) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('device.revenue')" width="130" align="right">
          <template #default="{ row }">
            <!-- 这一列一律是**售价**，部件行也一样：国内运费已经算在「总成本」里了，
                 在这儿再标一次扣完运费的净收入，等于同一笔运费在一行里出现两遍，
                 看的人会去减第二次。二级行的售价加起来正好等于整机那一行。 -->
            <span class="pcr-mono">{{ money(row.sale_cny) }}</span>
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
            <!-- 部件不算利润：成本不摊到单件，减不出来。这一格空着 -->
            <template v-if="row.kind !== 'part'">
              <span class="pcr-mono" :class="profitClass(row.profit_cny)">{{ money(row.profit_cny) }}</span>
              <el-tooltip v-if="row.incomplete" :content="t('card.incomplete')">
                <el-icon class="warn-icon"><WarningFilled /></el-icon>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
      </el-table>

      <div class="pager">
        <!-- 窄屏砍掉「共 N 条」和每页条数：整条分页器排不下一行，挤成两行之后翻页箭头
             会跑到第二行的两端，拇指够不着。页码数也从 7 收到 5。 -->
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          :layout="isMobile ? 'prev, pager, next' : 'total, sizes, prev, pager, next'"
          :pager-count="isMobile ? 5 : 7"
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
  Cpu, Filter, Monitor, Plus, Refresh, Search, WarningFilled
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
import PartTypeTag from '@/components/PartTypeTag.vue'

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

// 窄屏上除搜索框外的筛选器收在开关后面，只影响显示，不参与取数
const filtersOpen = ref(false)
// 开关按钮上的角标。不含关键词——搜索框一直摆在外面，它有没有值本来就看得见；
// 收起来的那几项才需要这个数提醒「现在看到的不是全部」。
const activeFilterCount = computed(() => {
  const f = filters
  return [f.kind, f.status.length ? f.status : null, f.brand, f.source_platform, dateRange.value]
    .filter(Boolean).length
})

// 手机上那两个单日期选择器写回同一个 dateRange。两头都清空时整个置回 null，
// 而不是留一个 [null, null]——filterParams 取的是 ?.[0] / ?.[1]，留着不影响取数，
// 但「筛选」角标数的是 dateRange 本身真不真，留着会一直显示有一项筛选在生效。
function setRangeEnd(i, value) {
  const next = [dateRange.value?.[0] || null, dateRange.value?.[1] || null]
  next[i] = value || null
  dateRange.value = next[0] || next[1] ? next : null
  reload()
}

// 手机卡片列表里展开了部件明细的整机行。用 row_key 而不是 id：显卡和整机的 id 各自
// 从 1 开始，混在一张列表里会互相顶掉（row_key 是后端规范化时就给好的唯一键）。
const expandedKeys = ref(new Set())
function togglePartsOf(row) {
  const next = new Set(expandedKeys.value)
  next.has(row.row_key) ? next.delete(row.row_key) : next.add(row.row_key)
  expandedKeys.value = next
}

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

// 表格里的金额：没有就空着，不摆「—」。空白在这张表里只有一个意思——这一格本来就
// 没有数据（还没卖、部件不摊成本）；真正算不出来的那种（缺汇率）由「利润」列右边的
// 警告图标标着，不靠破折号传达。
function money(value, fmt = cny) {
  return value === null || value === undefined ? '' : fmt(value)
}

// 二级行（部件）整行淡一档，一眼能看出层级
const rowClass = ({ row }) => (row.kind === 'part' ? 'part-row' : '')

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

/* ── 手机卡片列表 ──────────────────────────────────────────────────────
   一行摊成一张卡：上半是「这是什么」（封面 / 名称 / 类型 / 状态），中间一排是三个钱
   （成本 / 收入 / 利润），底下一行是日期。顺序照着人拿起手机想知道的顺序排，
   不是照桌面端的列序。 */
.m-list { display: flex; flex-direction: column; gap: 10px; }
.m-card {
  padding: 12px;
  border: 1px solid var(--pcr-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.015);
}
/* 按下去给一下反馈。整张卡都是点击区（全局关掉了 tap 高亮），不给反馈的话
   点完到路由跳转之间那一下会让人以为没点着，于是又点一次 */
.m-card:active { background: rgba(91, 140, 255, 0.08); }
.m-top { display: flex; gap: 10px; align-items: flex-start; }
/* 封面比桌面端大一档：手机上这张图常常是认出「哪张卡」最快的线索 */
.m-cover { width: 72px; height: 54px; flex: none; }
.m-head { flex: 1 1 auto; min-width: 0; }
.m-name { color: #e6edf7; font-size: 15px; font-weight: 500; line-height: 1.35; }
.m-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }

.m-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--pcr-border);
}
.m-metric { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.m-label { font-size: 11px; color: #8a94a6; }
/* 三个数都用等宽数字：三列上下对不齐的话，扫一眼看不出哪个大 */
.m-metric b { font-size: 15px; font-weight: 600; color: #e6edf7; }
.m-metric .m-sub { font-size: 11px; }

.m-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  font-size: 12px;
}
/* 展开按钮挤到右端，和左边的日期分开——它是个能按的东西，不该混在日期里 */
.m-expand {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: rgba(91, 140, 255, 0.1);
  color: #8fb8ff;
  font-size: 12px;
}
.m-parts { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.m-part {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 6px;
  background: rgba(91, 140, 255, 0.04);
  font-size: 12px;
}
.m-part-name { flex: 1 1 auto; min-width: 0; color: #b9c4d6; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-part-money { flex: none; color: #e6edf7; }

@media (max-width: 768px) {
  /* 展开后的五个筛选器各占满一行——并排只会各自剩下小半个框，看不清选的是什么。
     搜索框是例外：它和「筛选」开关共一行，收起状态下这一行就是全部筛选界面。 */
  .f-kind, .f-status, .f-brand, .f-platform, .f-date { width: 100% !important; }
  .filters { align-items: stretch; }
  .f-keyword { flex: 1 1 60%; width: auto !important; }
  .f-toggle { flex: 0 0 auto; margin-left: 0; }
  .f-add { flex: 1 1 100%; margin-left: 0; }
  /* 角标做成贴在文字后面的小圆点，不用 el-badge：badge 是绝对定位的，
     在按钮里会跑到边框外面被相邻控件盖住 */
  .f-count {
    margin-left: 5px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 8px;
    background: var(--pcr-accent);
    color: #fff;
    font-size: 11px;
    line-height: 16px;
    text-align: center;
  }
  /* 两张卡片并排在手机上只剩半屏宽，说明文字会碎成每行两三个字 */
  .add-picker { flex-direction: column; }
  /* 卡片列表自己带圆角和边框，外面那张卡的内边距只会白白吃掉两边各 12px */
  .table-card :deep(.el-card__body) { padding: 10px; }
  .pager { justify-content: center; }
}
</style>
